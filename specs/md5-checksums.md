# MD5 Checksums

## Purpose

Compute MD5 checksums for every photo in a project to enable duplicate detection and data integrity verification across systems.

## Definitions

- **Checksum**: The MD5 hash of a file's contents.
- **Checksum index**: A JSON file (`md5.json`) mapping file paths to their metadata and checksums.

## Behavior

### Standing convention: list, checksum, then archive

Every project source goes through the same steps, in order, not just photo
sources — decided 2026-07-19 when adding a non-photo source (a Google Drive
sync folder) to this tool's scope. **Order matters**: an earlier version of
this note said list → archive → checksum and that's wrong — checksumming a
large tree can run far longer than listing it, so archiving first can leave
nothing in `fetch/` for the checksum step to find by the time it starts.

1. **List.** Run the location's plain file-listing tool against the source
   root — `community.mac_file_dump` for a local filesystem path,
   `community.ios_file_registry` + `community.ios_file_dump` for a device
   over AFC. Cheap and fast (no content is read), so it surfaces structural
   surprises — a root that doesn't exist, an empty mount, an unexpectedly
   huge tree — before committing to the much slower, full-content checksum
   pass.
2. **Checksum**, while `fetch/` still holds this run's listing. Two ways to
   get there, both producing per-file digests — pick based on where the
   source was listed:
   - For a source listed via `community.mac_file_dump`, run
     `community.mac_file_dump/process_checksum_files.py` — it reads that same
     tool's `fetch/files.ndjson` by default and writes
     `fetch/files-checksums.ndjson` with **both** `md5` and `sha256` per
     file, one read pass for both digests. It also accepts an explicit
     `files.ndjson` path as an argument and writes its output next to
     whatever it's given — so if `fetch/` was already archived before this
     step ran, point it at the archived copy instead of re-listing. Added
     2026-07-19 alongside the Google Drive source; no zip is produced (see
     `community.mac_file_dump/Readme.txt`, script 5).
   - `photos_md5.py` (this spec, below) walks a project's declared
     `primary_storage`/`secondary_storage` directly and writes `md5.json`
     with **md5 only**. Still the path for sources whitelisted here
     (`Google Takeout`, `AndroidPhotoBackup`, `IPad`, `IPhone`,
     `MacPictures`, `GoogleDriveFolderOnMac`) that predate the
     `mac_file_dump`-integrated option, and for anything not going through
     `mac_file_dump`'s listing step at all. Not affected by this
     ordering note — it reads straight from the source, not from `fetch/`.
3. **Archive.** `community.mac_file_dump/archive_fetch.py <project_id>`
   moves everything now sitting in the tool's shared, get-overwritten-next-run
   `fetch/` directory — listing and checksums both — into the project's own
   `~/selfhosted/projects/<project_id>/fetched/<YYYY-MM-DD-HH-MM>/` —
   immutable, timestamped, never overwritten, so there's always a state to
   refer back to. This is the same convention `claude_web.py`'s pipeline
   already uses for Claude exports; `fetch/` on its own is scratch space,
   shared across whatever root was last pointed at it, not a durable record.

Between listing and checksumming, a broader sweep MAY be **seeded** from an
already-checksummed narrower project that sits inside it — e.g. a full `/`
sweep shouldn't re-hash the ~430GB already covered by the `macbook_maik_photos`
and `macbook_maik_googledrive` projects. `community.mac_file_dump/seed_checksums.py`
(Readme.txt script 7) rebases each seed entry's path onto the broader sweep's
own root (read back from its listing's meta line, not assumed to be `/`) and
writes it straight into `files-checksums.ndjson` ahead of the checksum step,
which then finds those entries already present via its normal resume logic
and skips them. Added 2026-07-19 alongside the whole-disk sweep project.

A full `/` sweep also needs Full Disk Access granted to the terminal running
it (System Settings -> Privacy & Security -> Full Disk Access) — without it,
`/Library`, other users' home directories, and TCC-gated app data come back
as inaccessible. `mac_file_dump`'s listing step no longer aborts on this (it
used to: `Path.rglob()` raises and loses the whole walk on the first
`PermissionError`) — it now skips the one inaccessible directory and records
it in `files.json`'s `"errors"` list instead, so an incomplete-due-to-permissions
sweep is visible rather than either crashing or silently under-counting.

The listing and the checksum answer different questions and both get kept:
"what's there and where" (path listing, feeds the locations registry's plain
inventory, `locations.md`) vs. "is this the same content as something
elsewhere" (checksum, feeds duplicate detection, `source-manifest.md`).

### Processing

1. For each photo project, check if `md5.json` already exists in the processed directory.
2. If `md5.json` exists, skip the project (already processed).
3. If not, walk the project's `fetched_folder` recursively.
4. For each file (excluding `.DS_Store`):
   - Read the file contents and compute the MD5 hash.
   - Record the file's absolute path, filename, MD5 checksum, and file size in bytes.
5. Write the complete checksum index to `md5.json`.

### Output Format

`md5.json` is a JSON object keyed by absolute file path:

```json
{
  "/path/to/photo.jpg": {
    "path": "/path/to/photo.jpg",
    "name": "photo.jpg",
    "md5sum": "d41d8cd98f00b204e9800998ecf8427e",
    "size": 1048576
  }
}
```

## Inputs

- A photo project with a `fetched_folder` containing files.

## Outputs

- `<processed_folder>/md5.json` — the checksum index for the project.

## Constraints

- `.DS_Store` files are excluded.
- Processing is idempotent — if `md5.json` exists, the project is skipped entirely.
- The JSON output is pretty-printed with 4-space indent, sorted keys, and non-ASCII characters preserved.

## Open Questions

- Should re-processing be supported (e.g., when new files are added to a project)?
- Should the hash algorithm be configurable (e.g., SHA-256 for stronger integrity guarantees)?
- Should file type filtering go beyond `.DS_Store` exclusion?
- Spec/code drift noticed 2026-07-19, not yet resolved: this spec says
  processing walks `fetched_folder` and writes to `<processed_folder>/md5.json`;
  the actual `photos_md5.py` walks `primary_storage`/`secondary_storage`
  directly and writes to `<project_folder>/photos_md5/md5.json`. Worth
  deciding which is authoritative rather than leaving both descriptions live.
- Unlike `claude_web.py`'s manifest (append-only, tracks fixity across every
  historical snapshot), `md5.json` is a single-shot index — once it exists,
  later runs only re-sample 10 files rather than re-checksumming or tracking
  change over time. Matching claude_web's fixity-over-time level for photo
  sources would be a real feature, not just a path fix — not done here,
  flagged for a decision.
