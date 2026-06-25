"""Generic Source Manifest builder — see specs/source-manifest.md.

A *manifest* is a per-source SQLite index: one row per item, recording a stable
locator, an MD5 fingerprint of the item's content, its size, and a few features.
Sources supply an *item iterator*; this module is the generic stage that consumes
it. Each item is a tuple:

    (kind, locator, locator_kind, content, features)

where `content` is either bytes or a filesystem path (streamed to compute the
fingerprint), and `features` is a JSON-serialisable mapping.
"""

import hashlib
import json
import os
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    seq          INTEGER PRIMARY KEY,
    kind         TEXT,            -- item type (e.g. "file")
    locator      TEXT,            -- address within the source (e.g. a path)
    locator_kind TEXT,            -- how to read the locator (e.g. "path")
    fingerprint  TEXT,            -- MD5 (hex) of the item's content
    size         INTEGER,         -- content size in bytes
    features     TEXT             -- JSON: source-specific attributes
);
CREATE INDEX IF NOT EXISTS idx_items_fingerprint ON items(fingerprint);
CREATE INDEX IF NOT EXISTS idx_items_locator     ON items(locator);
"""


def _md5_size(content):
    """Return (md5_hex, size_bytes) for `content` — bytes, or a path streamed off disk."""
    if isinstance(content, (bytes, bytearray)):
        return hashlib.md5(content).hexdigest(), len(content)
    with open(content, "rb") as fh:
        digest = hashlib.file_digest(fh, "md5").hexdigest()
    return digest, os.path.getsize(content)


def build(db_path, items, *, replace=True, commit_every=500):
    """Build a manifest at `db_path` from an item iterator. Returns the row count.

    Streaming: items are consumed and fingerprinted one at a time. A row whose
    content can't be read is still recorded (null fingerprint + an `error`
    feature) so one bad item never aborts the run.
    """
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if replace and db_path.exists():
        db_path.unlink()

    db = sqlite3.connect(db_path)
    db.executescript(SCHEMA)
    n = 0
    for kind, locator, locator_kind, content, features in items:
        feats = dict(features or {})
        try:
            fingerprint, size = _md5_size(content)
        except OSError as exc:
            fingerprint, size = None, None
            feats["error"] = repr(exc)
        db.execute(
            "INSERT INTO items (kind, locator, locator_kind, fingerprint, size, features) "
            "VALUES (?,?,?,?,?,?)",
            (kind, str(locator), locator_kind, fingerprint, size,
             json.dumps(feats, ensure_ascii=False, sort_keys=True)),
        )
        n += 1
        if n % commit_every == 0:
            db.commit()
    db.commit()
    db.close()
    return n
