#!/usr/bin/env python3
"""
Convert Claude conversation export (conversations.json) to an SQLite database
suitable for exploration in Datasette.
"""

import sqlite3
import json
from project_registry import load_projects

projects = load_projects()

def create_schema(db: sqlite3.Connection) -> None:
    db.executescript("""
        CREATE TABLE conversations (
            uuid        TEXT PRIMARY KEY,
            name        TEXT,
            summary     TEXT,
            created_at  TEXT,
            updated_at  TEXT,
            account_uuid TEXT
        );

        -- One row per chat_message in the export.
        -- 'text' is the flat string Claude already provides (full message text).
        CREATE TABLE messages (
            uuid                TEXT PRIMARY KEY,
            conversation_uuid   TEXT NOT NULL REFERENCES conversations(uuid),
            position            INTEGER NOT NULL,   -- 0-based order within conversation
            sender              TEXT,               -- 'human' | 'assistant'
            text                TEXT,               -- pre-rendered full text
            created_at          TEXT,
            updated_at          TEXT,
            parent_message_uuid TEXT
        );

        -- Individual content blocks inside a message (text, thinking, tool_use, tool_result …).
        CREATE TABLE content_blocks (
            id              INTEGER PRIMARY KEY,
            message_uuid    TEXT NOT NULL REFERENCES messages(uuid),
            position        INTEGER NOT NULL,       -- 0-based order within message
            type            TEXT,                   -- text | thinking | tool_use | tool_result | token_budget
            -- text / thinking blocks
            text            TEXT,
            -- tool_use blocks
            tool_name       TEXT,
            tool_input      TEXT,                   -- JSON string
            tool_message    TEXT,                   -- human-readable display message
            -- tool_result blocks
            tool_use_id     TEXT,
            tool_result_content TEXT,               -- JSON string
            is_error        INTEGER,                -- 0/1
            -- timestamps
            start_timestamp TEXT,
            stop_timestamp  TEXT
        );

        -- File attachments the human uploaded.
        CREATE TABLE attachments (
            id              INTEGER PRIMARY KEY,
            message_uuid    TEXT NOT NULL REFERENCES messages(uuid),
            position        INTEGER NOT NULL,
            file_name       TEXT,
            file_size       INTEGER,
            file_type       TEXT,
            extracted_content TEXT
        );

        -- File references (uuid-only entries with no extracted content).
        CREATE TABLE files (
            id              INTEGER PRIMARY KEY,
            message_uuid    TEXT NOT NULL REFERENCES messages(uuid),
            position        INTEGER NOT NULL,
            file_uuid       TEXT,
            file_name       TEXT
        );
    """)


def enable_fts(db: sqlite3.Connection) -> None:
    db.executescript("""
        CREATE VIRTUAL TABLE conversations_fts USING fts5(
            name, summary,
            content='conversations', content_rowid='rowid'
        );
        INSERT INTO conversations_fts(rowid, name, summary)
            SELECT rowid, name, summary FROM conversations;

        CREATE VIRTUAL TABLE messages_fts USING fts5(
            text,
            content='messages', content_rowid='rowid'
        );
        INSERT INTO messages_fts(rowid, text)
            SELECT rowid, text FROM messages WHERE text IS NOT NULL;

        CREATE VIRTUAL TABLE content_blocks_fts USING fts5(
            text, tool_name, tool_input, tool_message, tool_result_content,
            content='content_blocks', content_rowid='id'
        );
        INSERT INTO content_blocks_fts(rowid, text, tool_name, tool_input, tool_message, tool_result_content)
            SELECT id, text, tool_name, tool_input, tool_message, tool_result_content
            FROM content_blocks;
    """)


def insert_conversation(db: sqlite3.Connection, conv: dict) -> None:
    db.execute(
        "INSERT OR IGNORE INTO conversations VALUES (?,?,?,?,?,?)",
        (
            conv["uuid"],
            conv.get("name"),
            conv.get("summary"),
            conv.get("created_at"),
            conv.get("updated_at"),
            (conv.get("account") or {}).get("uuid"),
        ),
    )

    for pos, msg in enumerate(conv.get("chat_messages", [])):
        db.execute(
            "INSERT OR IGNORE INTO messages VALUES (?,?,?,?,?,?,?,?)",
            (
                msg["uuid"],
                conv["uuid"],
                pos,
                msg.get("sender"),
                msg.get("text"),
                msg.get("created_at"),
                msg.get("updated_at"),
                msg.get("parent_message_uuid"),
            ),
        )

        for cpos, block in enumerate(msg.get("content", [])):
            btype = block.get("type")

            text          = None
            tool_name     = None
            tool_input    = None
            tool_message  = None
            tool_use_id   = None
            tool_result_c = None
            is_error      = None

            if btype in ("text", "thinking"):
                text = block.get("text")

            elif btype == "tool_use":
                tool_name    = block.get("name")
                raw_input    = block.get("input")
                tool_input   = json.dumps(raw_input) if raw_input is not None else None
                tool_message = block.get("message")

            elif btype == "tool_result":
                tool_use_id   = block.get("tool_use_id")
                tool_name     = block.get("name")
                raw_content   = block.get("content")
                tool_result_c = json.dumps(raw_content) if raw_content is not None else None
                is_error      = int(bool(block.get("is_error")))

            db.execute(
                """INSERT INTO content_blocks
                   (message_uuid, position, type, text,
                    tool_name, tool_input, tool_message,
                    tool_use_id, tool_result_content, is_error,
                    start_timestamp, stop_timestamp)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    msg["uuid"], cpos, btype, text,
                    tool_name, tool_input, tool_message,
                    tool_use_id, tool_result_c, is_error,
                    block.get("start_timestamp"), block.get("stop_timestamp"),
                ),
            )

        for apos, att in enumerate(msg.get("attachments", [])):
            db.execute(
                "INSERT INTO attachments (message_uuid, position, file_name, file_size, file_type, extracted_content) VALUES (?,?,?,?,?,?)",
                (
                    msg["uuid"], apos,
                    att.get("file_name"),
                    att.get("file_size"),
                    att.get("file_type"),
                    att.get("extracted_content"),
                ),
            )

        for fpos, f in enumerate(msg.get("files", [])):
            db.execute(
                "INSERT INTO files (message_uuid, position, file_uuid, file_name) VALUES (?,?,?,?)",
                (msg["uuid"], fpos, f.get("file_uuid"), f.get("file_name")),
            )

def run(project):
    conversations = project['project_folder'] / 'fetched' / 'conversations.json'
    conversations_sqlite = project['project_folder'] / 'prompt_sqlite' / 'conversations.sqlite'

    print(f"Reading {conversations} ...")
    with conversations.open() as fh:
        data = json.load(fh)
    print(f"  {len(data)} conversations found.")

    if conversations_sqlite.exists():
        conversations_sqlite.unlink()

    db = sqlite3.connect(conversations_sqlite)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")

    create_schema(db)

    for conv in data:
        insert_conversation(db, conv)

    db.commit()

    print("Building full-text-search indexes …")
    enable_fts(db)
    db.commit()

    # Quick summary
    counts = {
        tbl: db.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
        for tbl in ("conversations", "messages", "content_blocks", "attachments", "files")
    }
    db.close()

    print(f"\nDone → {conversations_sqlite}")
    for tbl, n in counts.items():
        print(f"  {n:>6}  {tbl}")
    print()
    print("Open with:  datasette serve", conversations_sqlite)


def main():
    for projectid in projects.keys():
        project = projects[projectid]
        if project["source"] not in ["Prompts", ]:
            continue
        run(project)

if __name__ == "__main__":
    main()
