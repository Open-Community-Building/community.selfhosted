#!/usr/bin/env python3
"""
Convert a Claude conversation export (conversations.json) into SQLite for Datasette,
and run **per-message content fixity** across snapshots — see specs/claude_web.md.

Two passes per run:

1. **Conversion** — rebuild the per-snapshot SQLite (`conversations.sqlite`) from the
   latest snapshot's conversations.json. Plumbing is sqlite-utils.

2. **Content fixity** — maintain an append-only per-message manifest at
   `<project>/claude_web_manifest/manifest.sqlite`. Each Claude snapshot becomes an
   ingest; each *message* is an item with locator = message_uuid and checksum =
   SHA-256 of canonical message content (sender + text + content blocks +
   attachments + files + timestamps). Fixity_check across the two latest snapshots
   then classifies every message as added / unchanged / fixity_failure / dropped /
   loss. Growth (new messages in active conversations, new conversations) appears
   as `added` — not as a failure. Tampering (Claude edits an old message, deletes
   a conversation) appears as `fixity_failure` / `dropped` / `loss` — the loud
   alarm. On a clean run (no failures or losses), a `verified` event is recorded
   in the archive ledger for each archive_target, closing the **`verified`** leg
   of 3-2-1-1-0 compliance.
"""

import hashlib
import json
import re
from datetime import datetime, timezone

import sqlite_utils

import archive_ledger
import manifest
from location_identity import verify_pipeline_location
from project_registry import load_locations, select_projects

projects = select_projects()
locations = load_locations()

ALGORITHM = "sha256"                   # checksum algorithm for export provenance (matches the manifest)
_EPOCH_RE = re.compile(r"-(\d{10})-")  # the export's Unix epoch, embedded in the export zip filename


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


def _latest_snapshot(fetched):
    """The export snapshot folder (one holding conversations.json) that sorts last, or None.

    Snapshots are named by the export's embedded epoch (YYYY-MM-DD-HH-MM), so lexical
    order is chronological and the last is the most recent export.
    """
    if not fetched.is_dir():
        return None
    snaps = sorted(d for d in fetched.iterdir()
                   if d.is_dir() and (d / "conversations.json").is_file())
    return snaps[-1] if snaps else None


def _exported_at(snapshot):
    """The export's generation time (UTC ISO): from the snapshot's UTC name, else its zip, else None."""
    try:
        return datetime.strptime(snapshot.name, "%Y-%m-%d-%H-%M").replace(
            tzinfo=timezone.utc).isoformat()
    except ValueError:
        pass
    for zip_path in snapshot.glob("*.zip"):   # legacy: a zip kept alongside conversations.json
        m = _EPOCH_RE.search(zip_path.name)
        if m:
            return datetime.fromtimestamp(int(m.group(1)), tz=timezone.utc).isoformat()
    return None


def iter_message_items(data):
    """Yield manifest items per *message*, for cross-snapshot content fixity.

    Locator = `message_uuid` (stable; Claude assigns once at creation, doesn't reuse).
    Content for checksum = canonical JSON of the message body — sender, text,
    content blocks, attachments, files, timestamps. Same byte-for-byte JSON
    encoding (sort_keys, no spaces) means the SHA-256 is deterministic per message.
    Features = locating info that may legitimately change (conversation name,
    position) — captured for context, doesn't affect the checksum.

    Why per-message (not per-conversation):
    - New messages in an active conversation appear as `added` items (expected).
    - Genuine tampering (Claude edits/deletes/truncates an old message) is the
      only thing that registers as `fixity_failure` / `dropped` — actionable signal.
    A whole-conversation checksum would flag every active chat as a failure
    every snapshot, drowning the real signal.
    """
    for conv in data:
        conv_uuid = conv["uuid"]
        conv_name = conv.get("name")
        for pos, msg in enumerate(conv.get("chat_messages", []) or []):
            msg_uuid = msg.get("uuid")
            if not msg_uuid:
                continue
            canonical = json.dumps({
                "sender": msg.get("sender"),
                "text": msg.get("text"),
                "content": msg.get("content"),
                "attachments": msg.get("attachments"),
                "files": msg.get("files"),
                "created_at": msg.get("created_at"),
                "updated_at": msg.get("updated_at"),
            }, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
            features = {
                "conversation_uuid": conv_uuid,
                "conversation_name": conv_name,
                "position": pos,
                "sender": msg.get("sender"),
            }
            yield "message", msg_uuid, "uuid", canonical, features


def _ingested_snapshots(manifest_db):
    """Snapshot names already recorded as ingests in `manifest_db`."""
    if not manifest_db.exists():
        return set()
    db = sqlite_utils.Database(manifest_db)
    if not db["ingests"].exists():
        return set()
    return {r["source"] for r in db["ingests"].rows if r["source"]}


def _content_fixity(project, snapshots):
    """Backfill any missing snapshots into the per-message manifest and run
    fixity_check across the latest two. Returns the fixity report (or None on
    first-ingest, when there is nothing to compare).
    """
    manifest_db = project["project_folder"] / "claude_web_manifest" / "manifest.sqlite"
    already = _ingested_snapshots(manifest_db)
    to_ingest = [s for s in snapshots if s.name not in already]
    if not to_ingest:
        print(f"claude_web_manifest: no new snapshots to ingest "
              f"(manifest holds {len(already)})")
    else:
        if not already and len(to_ingest) > 1:
            print(f"claude_web_manifest: first run — backfilling "
                  f"{len(to_ingest)} snapshot(s) chronologically")
        for snap in to_ingest:
            data = json.loads((snap / "conversations.json").read_bytes())
            ingest_id, n = manifest.build(
                manifest_db, iter_message_items(data),
                source=snap.name, progress=False)
            print(f"  ingest {ingest_id}  snapshot {snap.name}  ({n:,} messages)")
    report = manifest.fixity_check(manifest_db)
    manifest.record_events(manifest_db, report)
    return report


def _emit_verified_for_project(project, snapshot_name):
    """Record a `verified` event in the archive ledger for each of the project's
    archive_targets after a clean per-message fixity_check.

    Honest scope: the fixity check verified the **source content** (the
    conversations.json the pipeline reads). The same content lives byte-identical
    at each archive_target via the rsync chain — we assert verified on that
    basis. Per-location independent re-verification (e.g. SFTP-hashing the
    Hetzner copy and comparing) is a stronger check left for a future stage.
    """
    pipeline_loc = None
    for tgt in project.get("archive_targets", []) or []:
        loc = locations.get(tgt["location"])
        if loc is None:
            continue
        if pipeline_loc is None and str(project["project_folder"]).startswith(
                str(loc.get("mount_point", "/this_will_never_match"))):
            pipeline_loc = loc["id"]
        is_source = (loc["id"] == pipeline_loc)
        note = (f"per-message fixity_check clean — snapshot {snapshot_name}"
                if is_source else
                f"inferred clean from source ({pipeline_loc}) — snapshot "
                f"{snapshot_name}; identical bytes via rsync chain")
        archive_ledger.record_event(
            kind="verified", location_id=loc["id"], project_id=project["id"],
            agent="claude_web.py", notes=note)


def run(project):
    fetched = project["project_folder"] / "fetched"
    snapshot = _latest_snapshot(fetched)
    conversations_json = (snapshot or fetched) / "conversations.json"
    if not conversations_json.is_file():
        print(f"{project['id']}: no conversations.json under {fetched}; skipping")
        return
    out = project["project_folder"] / "claude_web" / "conversations.sqlite"
    out.parent.mkdir(parents=True, exist_ok=True)

    raw = conversations_json.read_bytes()
    sha256 = hashlib.new(ALGORITHM, raw).hexdigest()
    data = json.loads(raw)
    print(f"Reading {conversations_json}")
    print(f"  snapshot={snapshot.name if snapshot else '(flat)'}  "
          f"sha256={sha256[:16]}…  {len(raw)} bytes  {len(data)} conversations")

    db = build(out, data)
    db["export"].insert({
        "snapshot": snapshot.name if snapshot else None,
        "sha256": sha256,
        "algorithm": ALGORITHM,
        "size_bytes": len(raw),
        "conversation_count": len(data),
        "exported_at": _exported_at(snapshot) if snapshot else None,
        "imported_at": datetime.now(timezone.utc).isoformat(),
    })

    print(f"\nDone -> {out}")
    for table in ("conversations", "messages", "content_blocks", "attachments", "files", "export"):
        if db[table].exists():
            print(f"  {db[table].count:>6}  {table}")

    # Content fixity across snapshots (per-message). Skip the legacy flat layout —
    # there's no snapshot history to track.
    if snapshot is None:
        return
    snapshots = sorted(d for d in fetched.iterdir()
                       if d.is_dir() and (d / "conversations.json").is_file())
    print()
    report = _content_fixity(project, snapshots)
    print(manifest.format_report(report))

    # On a clean fixity check, mark the project's archive_targets as `verified`.
    if report and not report["fixity_failure"] and not report["loss"]:
        _emit_verified_for_project(project, snapshot.name)


def main():
    for projectid in projects.keys():
        project = projects[projectid]
        if project["source"] not in ["Claude Web Prompts"]:
            continue
        verify_pipeline_location(project, locations)  # silent precondition; refuses on identity drift
        run(project)


if __name__ == "__main__":
    main()
