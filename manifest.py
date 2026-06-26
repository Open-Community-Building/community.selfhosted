"""Generic Source Manifest builder + fixity checking — see specs/source-manifest.md
and specs/fixity.md.

A *manifest* is a per-source SQLite index: one row per item, recording a stable
locator, a content **checksum** (message digest) plus its algorithm, the item's
size, and a few features. The checksum is the item's *fixity* value.

The manifest is **append-only**: each `build()` records a new *ingest* (a
timestamped run) and appends its items tagged with `ingest_id`, so successive
ingests stay comparable. `fixity_check()` diffs the two most recent ingests to
classify what was added, changed, dropped, moved, or lost.

Sources supply an *item iterator* yielding `(kind, locator, locator_kind, content,
features)` tuples, where `content` is bytes or a filesystem path (streamed to
compute the checksum). Plumbing is sqlite-utils.
"""

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import sqlite_utils

ALGORITHM = "md5"  # checksum algorithm, recorded per row (BagIt/PREMIS convention)


def _checksum_size(content):
    """Return (checksum_hex, size_bytes) for `content` — bytes, or a path streamed off disk."""
    if isinstance(content, (bytes, bytearray)):
        return hashlib.md5(content).hexdigest(), len(content)
    with open(content, "rb") as fh:
        digest = hashlib.file_digest(fh, "md5").hexdigest()
    return digest, os.path.getsize(content)


def _rows(items, ingest_id):
    """Turn (kind, locator, locator_kind, content, features) tuples into manifest rows.

    Streaming: items are consumed and checksummed one at a time. A row whose
    content can't be read is still emitted (null checksum + an `error` feature)
    so one bad item never aborts the run.
    """
    for seq, (kind, locator, locator_kind, content, features) in enumerate(items, start=1):
        feats = dict(features or {})
        try:
            checksum, size = _checksum_size(content)
        except OSError as exc:
            checksum, size = None, None
            feats["error"] = repr(exc)
        yield {
            "ingest_id": ingest_id,
            "seq": seq,
            "kind": kind,
            "locator": str(locator),
            "locator_kind": locator_kind,
            "checksum": checksum,
            "algorithm": ALGORITHM if checksum is not None else None,
            "size": size,
            "features": json.dumps(feats, ensure_ascii=False, sort_keys=True),
        }


def build(db_path, items, *, source=None):
    """Append a new ingest of `items` to the manifest. Returns (ingest_id, item_count).

    Append-only: the manifest is never recreated, so prior ingests remain for
    fixity comparison.
    """
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite_utils.Database(db_path)
    ingest_id = db["ingests"].insert(
        {"source": source,
         "run_at": datetime.now(timezone.utc).isoformat(),
         "algorithm": ALGORITHM,
         "item_count": 0},  # set below; 0 (not None) so the column is INTEGER
        pk="id").last_pk
    db["items"].insert_all(_rows(items, ingest_id), pk=("ingest_id", "seq"))  # streams in batches
    count = db["items"].count_where("ingest_id = ?", [ingest_id])
    db["ingests"].update(ingest_id, {"item_count": count})
    for col in ("checksum", "locator", "ingest_id"):
        db["items"].create_index([col], if_not_exists=True)
    return ingest_id, count


def _by_locator(db, ingest_id):
    return {r["locator"]: r for r in db["items"].rows_where("ingest_id = ?", [ingest_id])}


def fixity_check(db_path):
    """Diff the two most recent ingests. Returns a report dict, or None if <2 ingests.

    Two lenses: by locator (added / metadata_change / fixity_failure / dropped) and
    by checksum (a dropped locator whose checksum reappears elsewhere is a `moved`,
    one that appears nowhere is a `loss`).
    """
    db = sqlite_utils.Database(db_path)
    ids = [r["id"] for r in db["ingests"].rows_where(order_by="id")]
    if len(ids) < 2:
        return None
    prev_id, curr_id = ids[-2], ids[-1]
    old, new = _by_locator(db, prev_id), _by_locator(db, curr_id)
    new_checksums = {r["checksum"] for r in new.values() if r["checksum"]}

    added, unchanged, metadata_change, fixity_failure = [], [], [], []
    for loc, r in new.items():
        o = old.get(loc)
        if o is None:
            added.append(loc)
        elif r["checksum"] == o["checksum"]:
            (metadata_change if r["features"] != o["features"] else unchanged).append(loc)
        else:
            fixity_failure.append(loc)

    dropped, moved, loss = [], [], []
    for loc, r in old.items():
        if loc not in new:
            dropped.append(loc)
            (moved if r["checksum"] in new_checksums else loss).append(loc)

    return {
        "prev_ingest": prev_id, "curr_ingest": curr_id,
        "added": added, "unchanged": unchanged, "metadata_change": metadata_change,
        "fixity_failure": fixity_failure, "dropped": dropped, "moved": moved, "loss": loss,
    }


CLASSES = ("added", "unchanged", "metadata_change", "fixity_failure", "dropped", "moved", "loss")


def format_report(report):
    """A one-line per-class summary; the alarming classes (fixity_failure, loss) are listed out."""
    if report is None:
        return "fixity: first ingest — nothing to compare yet."
    head = (f"fixity: ingest {report['prev_ingest']} -> {report['curr_ingest']}  "
            + "  ".join(f"{c}={len(report[c])}" for c in CLASSES))
    alarms = [f"  ! {c}: {loc}" for c in ("fixity_failure", "loss") for loc in report[c]]
    return "\n".join([head, *alarms])
