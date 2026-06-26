# Claude Prompts

## Purpose

Turn Claude conversation exports into a queryable SQLite database for Datasette —
while keeping every export as an immutable, timestamped **snapshot** and recording
in the database exactly which export it was built from (the `conversations.json`
**SHA-256**), so a database's provenance is self-contained and a silently changed
export is detectable.

## Definitions

- **Export**: a Claude data export — a zip whose filename embeds the export's
  generation time as a Unix epoch (`data-…-<epoch>-…-batch-0000.zip`), unpacking to
  `conversations.json` plus `users.json`, `memories.json`, `projects/`, etc.
- **Snapshot**: one export's `conversations.json` kept immutably under
  `fetched/<YYYY-MM-DD-HH-MM>/`, the folder named for the export's **embedded epoch**
  (UTC). Produced by [Claude Ingest](claude_ingest.md) from a raw download; the raw
  zip itself stays in `claude_ingest/`. The epoch is the canonical temporal key (file
  mtimes are copy-unstable).
- **Checksum**: the SHA-256 of the `conversations.json` a build consumed — its
  provenance / fixity value, recorded in the database. Same algorithm as the
  [Source Manifest](source-manifest.md).

## Behavior

### Snapshots

1. Snapshots are produced by [Claude Ingest](claude_ingest.md): a raw export dropped
   in `claude_ingest/` becomes `fetched/<YYYY-MM-DD-HH-MM>/conversations.json`, the folder
   named from the export's embedded epoch (UTC), so folders sort chronologically.
2. Snapshots are immutable and hold only `conversations.json`; the raw zip stays in
   `claude_ingest/`.

### Selection

1. Process each project whose `source` is `Prompts`.
2. Read `conversations.json` from the **latest** snapshot — the snapshot folder that
   sorts last. If there are no snapshot folders, fall back to a flat
   `fetched/conversations.json` (the legacy layout).

### Conversion

1. Flatten the export's nested JSON into related tables — `conversations`,
   `messages`, `content_blocks`, `attachments`, `files` — with foreign keys and
   full-text search over the text-bearing columns.
2. The database is rebuilt from scratch each run; it reflects exactly one snapshot.

### Provenance

1. The build records, in a one-row **`export`** table, which export the database came
   from: the snapshot name, the **SHA-256** and byte size of the consumed
   `conversations.json`, its `algorithm`, the conversation count, the export time
   (`exported_at`, derived from the snapshot's UTC name), and the build time
   (`imported_at`).
2. This is the database's self-contained record of its source — enough to tell whether
   two databases came from the same export, and to notice a `conversations.json` that
   changed under a given snapshot.

## Inputs

- A `Prompts` project with one or more export snapshots under `fetched/` (or a legacy
  flat `fetched/conversations.json`).

## Outputs

- `<project_folder>/claude_prompts/conversations.sqlite` — the conversation tables and
  their FTS indexes, plus a one-row `export` provenance table `(snapshot, sha256,
  algorithm, size_bytes, conversation_count, exported_at, imported_at)`.

## Constraints

- Snapshots are immutable; the canonical temporal key is the embedded export epoch,
  not any file mtime.
- The checksum algorithm is **SHA-256**, consistent with the Source Manifest.
- The database is recreated per run and corresponds to exactly one snapshot.
- Read-only on the export; only the SQLite output is written.

## Open Questions

- Folder-name timezone: UTC (chosen — unambiguous, archival) vs local.
- Dedup on arrival: skip creating a snapshot when an incoming export's
  `conversations.json` checksum matches an existing snapshot's? (Raised, deferred.)
- Retention: keep every snapshot forever, or prune older ones once converted?
- Should a run ever convert *all* snapshots (history) rather than only the latest?
