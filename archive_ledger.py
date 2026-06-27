#!/usr/bin/env python3
"""
Cross-project events ledger — see specs/locations.md.

Append-only `events` table in `~/selfhosted/archive/archive.sqlite`. One row per
lifecycle/operational event on a location or project: `acquired`, `mounted`,
`migrated`, **`verified`** (content fixity passed — feeds compliance's `verified`
leg), **`verified_identity`** (container identity matched on use — provenance),
`decommissioned`, `deaccessioned`, `restored`, `disseminated`.

Plumbing is sqlite-utils, matching the rest of the codebase. The ledger is the
first cross-project SQLite (sibling of `projects/`, `locations/`, `story/`).
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import sqlite_utils

LEDGER_PATH = Path.home() / "selfhosted" / "archive" / "archive.sqlite"

EVENT_KINDS = (
    "acquired", "mounted", "migrated", "verified", "verified_identity",
    "decommissioned", "deaccessioned", "restored", "disseminated",
)


def db(path: Path = LEDGER_PATH) -> sqlite_utils.Database:
    """Open (and lazily create) the ledger database + parent dir."""
    path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite_utils.Database(path)


def record_event(kind: str, *, location_id: str | None = None,
                 project_id: str | None = None, agent: str | None = None,
                 notes: str | None = None, path: Path = LEDGER_PATH) -> int:
    """Append one event. Returns the row id. Closed-enum `kind` for predictability."""
    if kind not in EVENT_KINDS:
        raise ValueError(f"unknown event kind: {kind!r} (allowed: {EVENT_KINDS})")
    d = db(path)
    return d["events"].insert({
        "when_": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "kind": kind,
        "location_id": location_id,
        "project_id": project_id,
        "agent": agent,
        "notes": notes,
    }, pk="id", alter=True).last_pk


def latest_event(kind: str, *, location_id: str | None = None,
                 project_id: str | None = None,
                 path: Path = LEDGER_PATH) -> dict | None:
    """The most recent event matching `kind` and any provided scope. Or None."""
    if not path.exists():
        return None
    d = db(path)
    if not d["events"].exists():
        return None
    where, params = ["kind = ?"], [kind]
    if location_id is not None:
        where.append("location_id = ?"); params.append(location_id)
    if project_id is not None:
        where.append("project_id = ?"); params.append(project_id)
    rows = list(d["events"].rows_where(
        " AND ".join(where), params, order_by="id DESC", limit=1))
    return rows[0] if rows else None


def within(event: dict | None, days: int) -> bool:
    """True iff `event` exists and its `when_` is within the last `days` days."""
    if event is None or not event.get("when_"):
        return False
    when = datetime.fromisoformat(event["when_"])
    return datetime.now(timezone.utc) - when <= timedelta(days=days)
