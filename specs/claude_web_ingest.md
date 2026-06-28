# Claude Ingest

## Purpose

Turn a raw Claude export, dropped into a project's `claude_web_ingest/`, into a clean,
UTC-named **snapshot** under `fetched/` containing only the file the converter needs
— `conversations.json`. Adding a new export is "drop the zip and run": no manual
unzipping, no clutter.

## Definitions

- **Download**: a raw Claude export zip in `<project>/claude_web_ingest/`, named
  `data-…-<epoch>-…-batch-0000.zip`, where `<epoch>` is the export's Unix generation
  time. `conversations.json` is a top-level member.
- **Snapshot**: `<project>/fetched/<YYYY-MM-DD-HH-MM>/` — an immutable per-export
  folder named for the download's epoch (UTC), holding only `conversations.json`.
- **Needed member**: the single archive member the converter consumes,
  `conversations.json`. The rest (`users.json`, `memories.json`, `projects/`) stays
  inside the download.

## Behavior

### Detection

1. Process each project whose `source` is `Claude Web Prompts`.
2. Scan `<project>/claude_web_ingest/` for export zips.

### Snapshot creation

1. Derive the snapshot name from the **epoch embedded in the download's filename**,
   rendered `YYYY-MM-DD-HH-MM` in **UTC** — so snapshots sort chronologically and
   carry the canonical export time, independent of copy-unstable file mtimes.
2. If `fetched/<name>/conversations.json` already exists, **skip**. Ingestion is
   idempotent: re-running, or re-dropping the same export, does nothing.
3. Otherwise create `fetched/<name>/` and extract **only** `conversations.json` from
   the zip into it. The raw download is left in `claude_web_ingest/` as the archived original.

### Robustness

1. A download whose filename carries no epoch is skipped with a warning (it can't be
   named canonically).
2. A download with no `conversations.json` member is skipped with a warning.

## Inputs

- A `Claude Web Prompts` project with a `claude_web_ingest/` folder holding one or more raw export zips.

## Outputs

- One `fetched/<YYYY-MM-DD-HH-MM>/conversations.json` per export — consumed by
  [Claude Web Prompts](claude_web.md).

## Constraints

- The snapshot is named by the **UTC** export epoch, not any file mtime.
- Only `conversations.json` is extracted; the rest of the export stays zipped in
  `claude_web_ingest/`, which is never deleted (it is the raw archive).
- Idempotent and read-only on the download — extraction never modifies the zip.

## Open Questions

- Fully-automatic ingestion: wrap the command in a `launchd` / `fswatch` watch on
  `claude_web_ingest/`, or is running it (directly or on a schedule) enough?
- Extract more than `conversations.json` if a future feature needs it (e.g.
  `memories.json`, `projects/`), or keep snapshots minimal?
- Prune or relocate a download once ingested, or keep `claude_web_ingest/` as the full raw
  archive (current)?
