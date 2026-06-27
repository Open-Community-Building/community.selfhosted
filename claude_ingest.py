#!/usr/bin/env python3
"""
Acquire Claude exports — see specs/claude_ingest.md.

Each `Prompts` project has a `claude_ingest/` drop-zone for raw export zips
(`data-…-<epoch>-…-batch-0000.zip`). For any download not yet unpacked, create a
UTC-named snapshot under `fetched/` holding only the file the converter needs,
`conversations.json`. The <epoch> in the filename (the export's Unix generation
time) names the snapshot, so folders sort chronologically and carry the canonical
export time. Idempotent: a download whose snapshot already exists is skipped; the
raw zip is left in `claude_ingest/` as the archived original.
"""

import re
import shutil
import zipfile
from datetime import datetime, timezone

from location_identity import verify_pipeline_location
from project_registry import load_locations, select_projects

projects = select_projects()
locations = load_locations()

NEEDED = "conversations.json"           # the only member the converter consumes
_EPOCH_RE = re.compile(r"-(\d{10})-")   # the export's Unix epoch, embedded in the zip name


def _snapshot_name(zip_path):
    """UTC snapshot name (YYYY-MM-DD-HH-MM) from the epoch in the zip filename, or None."""
    m = _EPOCH_RE.search(zip_path.name)
    if not m:
        return None
    return datetime.fromtimestamp(int(m.group(1)), tz=timezone.utc).strftime("%Y-%m-%d-%H-%M")


def _member(zf, name):
    """The archive member named exactly `name` or ending in `/name`, or None."""
    for info in zf.infolist():
        if info.filename == name or info.filename.endswith("/" + name):
            return info
    return None


def ingest_zip(zip_path, fetched):
    """Extract NEEDED from one download into fetched/<utc>/. Returns True if newly unpacked."""
    name = _snapshot_name(zip_path)
    if name is None:
        print(f"  ! {zip_path.name}: no export epoch in filename; skipping")
        return False
    target = fetched / name / NEEDED
    if target.exists():
        return False                    # already unpacked — idempotent
    with zipfile.ZipFile(zip_path) as zf:
        info = _member(zf, NEEDED)
        if info is None:
            print(f"  ! {zip_path.name}: no {NEEDED} inside; skipping")
            return False
        target.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(info) as src, open(target, "wb") as dst:
            shutil.copyfileobj(src, dst)
    print(f"  + {zip_path.name} -> fetched/{name}/{NEEDED}")
    return True


def run(project):
    claude_ingest = project["project_folder"] / "claude_ingest"
    fetched = project["project_folder"] / "fetched"
    if not claude_ingest.is_dir():
        print(f"{project['id']}: no claude_ingest/ ; skipping")
        return
    zips = sorted(claude_ingest.glob("*.zip"))
    new = sum(ingest_zip(z, fetched) for z in zips)
    print(f"{project['id']}: {len(zips)} export(s) in claude_ingest/, {new} newly unpacked")


def main():
    for projectid in projects.keys():
        project = projects[projectid]
        if project["source"] not in ["Prompts"]:
            continue
        verify_pipeline_location(project, locations)  # silent precondition; refuses on identity drift
        run(project)


if __name__ == "__main__":
    main()
