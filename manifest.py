"""Generic Source Manifest builder + fixity checking — see specs/source-manifest.md
and specs/fixity.md.

A *manifest* is a per-source SQLite index: one row per item, recording a stable
locator, a content **checksum** (message digest) plus its algorithm, the item's
size, and a few features. The checksum is the item's *fixity* value.

The manifest is **append-only**: each `build()` records a new *ingest* (a
timestamped run) and appends its items tagged with `ingest_id`, so successive
ingests stay comparable. `fixity_check()` diffs the two most recent ingests to
classify what was added, changed, dropped, moved, lost, or rehashed (re-checksummed
under a new algorithm).

Sources supply an *item iterator* yielding `(kind, locator, locator_kind, content,
features)` tuples, where `content` is bytes or a filesystem path (streamed to
compute the checksum). Plumbing is sqlite-utils.
"""

import hashlib
import json
import os
import sys
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from itertools import islice
from pathlib import Path

import sqlite_utils

ALGORITHM = "sha256"  # checksum algorithm, recorded per row (BagIt/PREMIS); switching is
                      # safe — fixity_check compares within an algorithm (see `rehashed`)


def _checksum_size(content):
    """Return (checksum_hex, size_bytes) for `content` — bytes, or a path streamed off disk.

    Hashes with ALGORITHM; a file path is streamed so large files aren't read into memory.
    """
    if isinstance(content, (bytes, bytearray)):
        return hashlib.new(ALGORITHM, content).hexdigest(), len(content)
    with open(content, "rb") as fh:
        digest = hashlib.file_digest(fh, ALGORITHM).hexdigest()
    return digest, os.path.getsize(content)


def _hash_item(item):
    """Thread worker: item tuple -> (item, checksum, size, error). Reads + hashes content."""
    try:
        checksum, size = _checksum_size(item[3])      # item[3] is `content` (bytes or path)
        return item, checksum, size, None
    except OSError as exc:
        return item, None, None, repr(exc)


def _parallel_ordered(fn, items, workers):
    """Apply fn across `workers` threads, yielding results in input order with at most
    ~2x workers tasks in flight — so indexing stays streaming and memory-bounded."""
    it = iter(items)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        pending = deque()
        for _ in range(workers * 2):
            try:
                pending.append(ex.submit(fn, next(it)))
            except StopIteration:
                break
        while pending:
            result = pending.popleft().result()
            try:
                pending.append(ex.submit(fn, next(it)))
            except StopIteration:
                pass
            yield result


def _rows(items, ingest_id, workers=1):
    """Turn (kind, locator, locator_kind, content, features) tuples into manifest rows.

    Items are hashed across `workers` threads — the SHA-256 and file read release the
    GIL, so this uses multiple cores — and results are emitted in **input order**, so
    `seq` and the capped "first N" stay deterministic. Streaming and memory-bounded
    either way. A row whose content can't be read is still emitted (null checksum + an
    `error` feature) so one bad item never aborts the run.
    """
    hashed = (_parallel_ordered(_hash_item, items, workers) if workers and workers > 1
              else (_hash_item(it) for it in items))
    for seq, (item, checksum, size, error) in enumerate(hashed, start=1):
        kind, locator, locator_kind, content, features = item
        feats = dict(features or {})
        if error is not None:
            feats["error"] = error
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


def _human(n):
    """Human-readable byte count."""
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


def _hms(seconds):
    """Seconds → H:MM:SS."""
    s = int(seconds)
    return f"{s // 3600}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def _with_progress(rows, *, total=None, label="", every=0.5):
    """Pass manifest rows through, printing a throttled one-line progress to stderr (\\r).

    `total` (when known) adds a percentage and ETA; `label` (the source) prefixes the
    line so it's clear which project is running.
    """
    pre = f"{label}: " if label else ""
    start = last = time.time()
    n = nbytes = 0
    for row in rows:
        n += 1
        nbytes += row.get("size") or 0
        now = time.time()
        if now - last >= every:
            last = now
            elapsed = now - start
            rate = nbytes / max(elapsed, 1e-9)
            if total:
                count = f"{n:,}/{total:,} ({100 * n // total}%)"
                tail = f" · ETA {_hms((total - n) * elapsed / max(n, 1))}"
            else:
                count, tail = f"{n:,} items", ""
            sys.stderr.write(f"\r  {pre}indexing {count} · {_human(nbytes)} · "
                             f"{_human(rate)}/s · {_hms(elapsed)}{tail}    ")
            sys.stderr.flush()
        yield row
    dt = time.time() - start
    sys.stderr.write(f"\r  {pre}indexed {n:,} items · {_human(nbytes)} · "
                     f"{_human(nbytes / max(dt, 1e-9))}/s · in {_hms(dt)}\n")
    sys.stderr.flush()


def build(db_path, items, *, source=None, limit=None, total=None, workers=1, progress=True):
    """Append a new ingest of `items` to the manifest. Returns (ingest_id, item_count).

    Append-only: the manifest is never recreated, so prior ingests remain for
    fixity comparison. `limit` caps the run to the first N items (a partial run, for
    fast iteration or a first look); it is recorded on the ingest as `item_limit`.
    `workers` hashes items across that many threads (>1 uses multiple cores; input
    order and `seq` are preserved). `progress` prints a throttled one-line progress to
    stderr (labelled with `source`, with a percentage/ETA when `total` is given).
    """
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite_utils.Database(db_path)
    ingest_id = db["ingests"].insert(
        {"source": source,
         "run_at": datetime.now(timezone.utc).isoformat(),
         "algorithm": ALGORITHM,
         "item_limit": limit,
         "item_count": 0},  # set below; 0 (not None) so the column is INTEGER
        pk="id").last_pk
    if limit is not None:
        items = islice(items, limit)
    rows = _rows(items, ingest_id, workers=workers)
    if progress:
        caps = [c for c in (total, limit) if c is not None]
        rows = _with_progress(rows, total=min(caps) if caps else None, label=source or "")
    db["items"].insert_all(rows, pk=("ingest_id", "seq"))  # streams in batches
    count = db["items"].count_where("ingest_id = ?", [ingest_id])
    db["ingests"].update(ingest_id, {"item_count": count})
    for col in ("checksum", "locator", "ingest_id"):
        db["items"].create_index([col], if_not_exists=True)
    return ingest_id, count


def ingest_count(db_path):
    """How many ingests the manifest already holds (0 if it doesn't exist yet)."""
    db_path = Path(db_path)
    if not db_path.exists():
        return 0
    db = sqlite_utils.Database(db_path)
    return db["ingests"].count if db["ingests"].exists() else 0


def _by_locator(db, ingest_id):
    return {r["locator"]: r for r in db["items"].rows_where("ingest_id = ?", [ingest_id])}


def fixity_check(db_path):
    """Diff the two most recent ingests. Returns a report dict, or None if <2 ingests.

    Two lenses: by locator (added / metadata_change / fixity_failure / rehashed /
    dropped) and by checksum (a dropped locator whose checksum reappears elsewhere is
    a `moved`, one that appears nowhere is a `loss`).

    Comparison is per-algorithm: checksums are only comparable when computed with the
    same algorithm. A locator whose algorithm changed between ingests (e.g. an
    md5 -> sha256 migration) is `rehashed` — its integrity can't be judged by checksum
    here, so it is never mistaken for a fixity failure.
    """
    db = sqlite_utils.Database(db_path)
    ids = [r["id"] for r in db["ingests"].rows_where(order_by="id")]
    if len(ids) < 2:
        return None
    prev_id, curr_id = ids[-2], ids[-1]
    old, new = _by_locator(db, prev_id), _by_locator(db, curr_id)
    # Match content only within the same algorithm: an (algorithm, checksum) pair.
    new_digests = {(r["algorithm"], r["checksum"]) for r in new.values() if r["checksum"]}

    added, unchanged, metadata_change, fixity_failure, rehashed = [], [], [], [], []
    for loc, r in new.items():
        o = old.get(loc)
        if o is None:
            added.append(loc)
        elif o["algorithm"] != r["algorithm"]:
            rehashed.append(loc)
        elif r["checksum"] == o["checksum"]:
            (metadata_change if r["features"] != o["features"] else unchanged).append(loc)
        else:
            fixity_failure.append(loc)

    dropped, moved, loss = [], [], []
    for loc, r in old.items():
        if loc not in new:
            dropped.append(loc)
            (moved if (r["algorithm"], r["checksum"]) in new_digests else loss).append(loc)

    return {
        "prev_ingest": prev_id, "curr_ingest": curr_id,
        "added": added, "unchanged": unchanged, "metadata_change": metadata_change,
        "fixity_failure": fixity_failure, "rehashed": rehashed,
        "dropped": dropped, "moved": moved, "loss": loss,
    }


CLASSES = ("added", "unchanged", "metadata_change", "fixity_failure", "rehashed", "dropped", "moved", "loss")

# Events worth an audit row: `unchanged` is a no-op, and `dropped` is the unresolved
# superset of `moved`/`loss`, so neither is logged to `fixity_events`.
EVENT_CLASSES = ("added", "metadata_change", "fixity_failure", "rehashed", "moved", "loss")


def format_report(report):
    """A one-line per-class summary; the alarming classes (fixity_failure, loss) are listed out."""
    if report is None:
        return "fixity: first ingest — nothing to compare yet."
    head = (f"fixity: ingest {report['prev_ingest']} -> {report['curr_ingest']}  "
            + "  ".join(f"{c}={len(report[c])}" for c in CLASSES))
    alarms = [f"  ! {c}: {loc}" for c in ("fixity_failure", "loss") for loc in report[c]]
    return "\n".join([head, *alarms])


def record_events(db_path, report):
    """Append a fixity report's notable events to a `fixity_events` audit table.

    `fixity_check` only ever compares the two latest ingests; calling this after each
    ingest accumulates a durable provenance log (queryable in Datasette) that outlives
    that single comparison. Idempotent — re-recording an ingest inserts nothing new.
    Returns the number of events in the report (0 on the first ingest, nothing to compare).
    """
    if report is None:
        return 0
    db = sqlite_utils.Database(db_path)
    prev, curr = report["prev_ingest"], report["curr_ingest"]
    old, new = _by_locator(db, prev), _by_locator(db, curr)
    rows = [
        {"ingest_id": curr, "prev_ingest": prev, "locator": loc, "class": cls,
         "old_checksum": (old.get(loc) or {}).get("checksum"),
         "new_checksum": (new.get(loc) or {}).get("checksum")}
        for cls in EVENT_CLASSES for loc in report[cls]
    ]
    if rows:
        db["fixity_events"].insert_all(
            rows, pk=("ingest_id", "locator"),
            foreign_keys=[("ingest_id", "ingests", "id"), ("prev_ingest", "ingests", "id")],
            ignore=True)
        db["fixity_events"].create_index(["class"], if_not_exists=True)
    return len(rows)
