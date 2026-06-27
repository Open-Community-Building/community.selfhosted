"""Build the Source Manifest for each photo project — see specs/source-manifest.md
and specs/fixity.md.

The photos *item iterator*: one item per file under a project's storage folder,
yielding the file path as the locator and the file itself as content. The generic
`manifest.build` checksums each file and appends a new *ingest* to a standalone
SQLite index at `photos_manifest/manifest.sqlite`; a fixity check against the
previous ingest is reported at the end of each run.
"""

import os
from datetime import datetime, timezone

import archive_ledger
import manifest
from location_identity import pipeline_location_for
from project_registry import load_locations, select_projects

projects = select_projects()
locations = load_locations()

PHOTO_SOURCES = ["Google Takeout", "AndroidPhotoBackup", "IPad", "IPhone", 'MacPictures']

# Optional cap for partial runs / iteration: `MANIFEST_LIMIT=200 weasel run manifest`.
LIMIT = int(os.environ["MANIFEST_LIMIT"]) if os.environ.get("MANIFEST_LIMIT") else None

# Hashing threads — SHA-256 + file reads release the GIL, so this uses multiple cores.
# Tune to your volume: `MANIFEST_WORKERS=8 weasel run manifest` (1 = sequential).
WORKERS = int(os.environ.get("MANIFEST_WORKERS") or min(4, os.cpu_count() or 4))


def iter_photo_items(folder):
    """Yield (kind, locator, locator_kind, content, features) per file under `folder`.

    content is the file path — manifest.build streams it to compute the checksum.
    """
    for directory, dirs, files in os.walk(folder):
        dirs.sort()                      # deterministic traversal, so a capped run is reproducible
        for name in sorted(files):
            if name.endswith(".DS_Store"):
                continue
            path = os.path.join(directory, name)
            ext = os.path.splitext(name)[1].lower()
            try:
                mtime = datetime.fromtimestamp(
                    os.path.getmtime(path), tz=timezone.utc).isoformat()
            except OSError:
                mtime = None
            yield "file", path, "path", path, {"ext": ext, "mtime": mtime}


def _count_files(folder):
    """Count indexable files under `folder` (excludes .DS_Store) — the progress total."""
    return sum(1 for _, _, files in os.walk(folder)
               for f in files if not f.endswith(".DS_Store"))


def process(project):
    folder = project["primary_storage"] or project["secondary_storage"]
    db_path = project["project_folder"] / "photos_manifest" / "manifest.sqlite"
    prior = manifest.ingest_count(db_path)
    where = f"ingest {prior + 1}" + (f" (appending to {prior} prior)" if prior else " (first)")
    if LIMIT:                                   # capped run: total is just the cap, no pre-scan
        total, scope = None, f"up to {LIMIT:,} items (capped)"
    else:                                       # full run: pre-scan for the total (→ % and ETA)
        print(f"{project['id']}: scanning {folder} …", flush=True)
        total = _count_files(folder)
        scope = f"{total:,} files"
    print(f"{project['id']}: {where} · {scope} · {WORKERS} thread(s) -> {db_path}")
    ingest_id, n = manifest.build(db_path, iter_photo_items(folder),
                                  source=project["id"], limit=LIMIT, total=total, workers=WORKERS)
    print(f"{project['id']}: indexed {n:,} items (ingest {ingest_id})")
    report = manifest.fixity_check(db_path)
    manifest.record_events(db_path, report)     # append this ingest's events to the audit log
    print(manifest.format_report(report))

    # On a clean fixity_check (no fixity_failure, no loss), record a `verified`
    # event in the cross-project ledger for the pipeline's location — that is
    # what feeds compliance.py's `verified` leg (the "0 errors" of 3-2-1-1-0).
    # A first ingest has nothing to compare against → no event yet.
    if report and not report["fixity_failure"] and not report["loss"]:
        location, _ = pipeline_location_for(project, locations)
        if location is not None:
            archive_ledger.record_event(
                kind="verified",
                location_id=location["id"],
                project_id=project["id"],
                agent="manifest.py",
                notes=f"fixity_check clean — ingest {ingest_id} ({n} items)",
            )


def main():
    for projectid in projects.keys():
        project = projects[projectid]
        if project["source"] not in PHOTO_SOURCES:
            continue
        # Opt-in per project, mirroring photos_md5: only build where the
        # photos_manifest/ directory has been created.
        if (project["project_folder"] / "photos_manifest").is_dir():
            process(project)


if __name__ == "__main__":
    main()
