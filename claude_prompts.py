#!/usr/bin/env python3
"""
Convert a Claude conversation export (conversations.json) into SQLite for Datasette.

Plumbing is sqlite-utils: tables, foreign keys and FTS are built from the row
dicts rather than hand-written SQL. The only bespoke part is the mapping from the
export's nested JSON to flat rows.
"""

import json

import sqlite_utils
from project_registry import load_projects

projects = load_projects()


def _content_block(message_uuid, position, block):
    """One content_blocks row from a message's content block (text/thinking/tool_*)."""
    btype = block.get("type")
    row = {
        "message_uuid": message_uuid,
        "position": position,
        "type": btype,
        "text": None,
        "tool_name": None,
        "tool_input": None,
        "tool_message": None,
        "tool_use_id": None,
        "tool_result_content": None,
        "is_error": None,
        "start_timestamp": block.get("start_timestamp"),
        "stop_timestamp": block.get("stop_timestamp"),
    }
    if btype in ("text", "thinking"):
        row["text"] = block.get("text")
    elif btype == "tool_use":
        row["tool_name"] = block.get("name")
        raw = block.get("input")
        row["tool_input"] = json.dumps(raw) if raw is not None else None
        row["tool_message"] = block.get("message")
    elif btype == "tool_result":
        row["tool_use_id"] = block.get("tool_use_id")
        row["tool_name"] = block.get("name")
        raw = block.get("content")
        row["tool_result_content"] = json.dumps(raw) if raw is not None else None
        row["is_error"] = int(bool(block.get("is_error")))
    return row


def to_rows(data):
    """Flatten the export into (conversations, messages, content_blocks, attachments, files)."""
    conversations, messages, content_blocks, attachments, files = [], [], [], [], []
    for conv in data:
        conversations.append({
            "uuid": conv["uuid"],
            "name": conv.get("name"),
            "summary": conv.get("summary"),
            "created_at": conv.get("created_at"),
            "updated_at": conv.get("updated_at"),
            "account_uuid": (conv.get("account") or {}).get("uuid"),
        })
        for pos, msg in enumerate(conv.get("chat_messages", [])):
            messages.append({
                "uuid": msg["uuid"],
                "conversation_uuid": conv["uuid"],
                "position": pos,
                "sender": msg.get("sender"),
                "text": msg.get("text"),
                "created_at": msg.get("created_at"),
                "updated_at": msg.get("updated_at"),
                "parent_message_uuid": msg.get("parent_message_uuid"),
            })
            for cpos, block in enumerate(msg.get("content", [])):
                content_blocks.append(_content_block(msg["uuid"], cpos, block))
            for apos, att in enumerate(msg.get("attachments", [])):
                attachments.append({
                    "message_uuid": msg["uuid"],
                    "position": apos,
                    "file_name": att.get("file_name"),
                    "file_size": att.get("file_size"),
                    "file_type": att.get("file_type"),
                    "extracted_content": att.get("extracted_content"),
                })
            for fpos, f in enumerate(msg.get("files", [])):
                files.append({
                    "message_uuid": msg["uuid"],
                    "position": fpos,
                    "file_uuid": f.get("file_uuid"),
                    "file_name": f.get("file_name"),
                })
    return conversations, messages, content_blocks, attachments, files


def build(db_path, data):
    """Build the SQLite database at db_path from the parsed export `data`."""
    convs, msgs, blocks, atts, fs = to_rows(data)
    db = sqlite_utils.Database(db_path, recreate=True)

    db["conversations"].insert_all(convs, pk="uuid")
    db["messages"].insert_all(
        msgs, pk="uuid",
        foreign_keys=[("conversation_uuid", "conversations", "uuid")])
    db["content_blocks"].insert_all(
        blocks, foreign_keys=[("message_uuid", "messages", "uuid")])
    db["attachments"].insert_all(
        atts, foreign_keys=[("message_uuid", "messages", "uuid")])
    db["files"].insert_all(
        fs, foreign_keys=[("message_uuid", "messages", "uuid")])

    if convs:
        db["conversations"].enable_fts(["name", "summary"])
    if msgs:
        db["messages"].enable_fts(["text"])
    if blocks:
        db["content_blocks"].enable_fts(
            ["text", "tool_name", "tool_input", "tool_message", "tool_result_content"])
    return db


def run(project):
    conversations_json = project["project_folder"] / "fetched" / "conversations.json"
    out = project["project_folder"] / "claude_prompts" / "conversations.sqlite"
    out.parent.mkdir(parents=True, exist_ok=True)

    print(f"Reading {conversations_json} ...")
    data = json.loads(conversations_json.read_text())
    print(f"  {len(data)} conversations found.")

    db = build(out, data)

    print(f"\nDone -> {out}")
    for table in ("conversations", "messages", "content_blocks", "attachments", "files"):
        if db[table].exists():
            print(f"  {db[table].count:>6}  {table}")


def main():
    for projectid in projects.keys():
        project = projects[projectid]
        if project["source"] not in ["Prompts"]:
            continue
        run(project)


if __name__ == "__main__":
    main()
