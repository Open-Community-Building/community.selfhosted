"""Generic Source Manifest builder — see specs/source-manifest.md.

A *manifest* is a per-source SQLite index: one row per item, recording a stable
locator, an MD5 fingerprint of the item's content, its size, and a few features.
Sources supply an *item iterator*; this module is the generic stage that consumes
it. Each item is a tuple:

    (kind, locator, locator_kind, content, features)

where `content` is either bytes or a filesystem path (streamed to compute the
fingerprint), and `features` is a JSON-serialisable mapping. Plumbing is
sqlite-utils.
"""

import hashlib
import json
import os
from pathlib import Path

import sqlite_utils


def _md5_size(content):
    """Return (md5_hex, size_bytes) for `content` — bytes, or a path streamed off disk."""
    if isinstance(content, (bytes, bytearray)):
        return hashlib.md5(content).hexdigest(), len(content)
    with open(content, "rb") as fh:
        digest = hashlib.file_digest(fh, "md5").hexdigest()
    return digest, os.path.getsize(content)


def _rows(items):
    """Turn (kind, locator, locator_kind, content, features) tuples into manifest rows.

    Streaming: items are consumed and fingerprinted one at a time. A row whose
    content can't be read is still emitted (null fingerprint + an `error`
    feature) so one bad item never aborts the run.
    """
    for seq, (kind, locator, locator_kind, content, features) in enumerate(items, start=1):
        feats = dict(features or {})
        try:
            fingerprint, size = _md5_size(content)
        except OSError as exc:
            fingerprint, size = None, None
            feats["error"] = repr(exc)
        yield {
            "seq": seq,
            "kind": kind,
            "locator": str(locator),
            "locator_kind": locator_kind,
            "fingerprint": fingerprint,
            "size": size,
            "features": json.dumps(feats, ensure_ascii=False, sort_keys=True),
        }


def build(db_path, items, *, replace=True):
    """Build a manifest at `db_path` from an item iterator. Returns the row count."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite_utils.Database(db_path, recreate=replace)
    db["items"].insert_all(_rows(items), pk="seq")  # streams in batches
    if not db["items"].exists():
        return 0
    db["items"].create_index(["fingerprint"], if_not_exists=True)
    db["items"].create_index(["locator"], if_not_exists=True)
    return db["items"].count
