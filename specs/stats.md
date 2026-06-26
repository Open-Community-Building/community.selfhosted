# Stats

## Purpose

Generate statistics for each photo project to provide an overview of the inventory and support reporting across systems.

## Definitions

- **Stats file**: A JSON file (`stats.json`) containing computed statistics for a single project.

## Behavior

### Processing

1. For each photo project that has a [Source Manifest](source-manifest.md)
   (`photos_manifest/manifest.sqlite`), read it.
2. Compute the statistics from the manifest's `items` table and (re)write them to
   `stats.json`.

### Computed Statistics

| Stat | Description |
|------|-------------|
| `total` | Total number of items in the manifest |
| `total_size` | Sum of all item sizes in bytes |
| `total_size_human` | Human-readable representation of `total_size` (e.g., `"1.2 GB"`) |
| `types` | Object mapping lowercase file extensions to their count |

### Total Size

1. Sum the `size` of every item in the manifest.
2. Store the raw byte count as `total_size`.
3. Convert to a human-readable string as `total_size_human` using binary units: B, KB, MB, GB, TB. Use one decimal place (e.g., `"1.2 GB"`, `"843.5 MB"`). Use the largest unit where the value is >= 1.

### File Type Breakdown

1. For each item in the manifest, read its `ext` feature — the file extension,
   already normalised to lowercase at manifest time (e.g., `.JPG` → `.jpg`).
2. Items with no extension carry `ext` `""` and are counted under the key `""`.
3. Produce an object mapping each extension to its count, sorted by key.

### Output Format

```json
{
  "total": 1234,
  "total_size": 1288490188,
  "total_size_human": "1.2 GB",
  "types": {
    ".heic": 42,
    ".jpg": 900,
    ".png": 292
  }
}
```

## Inputs

- A project's [Source Manifest](source-manifest.md) (`photos_manifest/manifest.sqlite`) — must exist before stats can be generated.

## Outputs

- `<project_folder>/photos_stats/stats.json` — statistics for the project.

## Constraints

- Stats depend on the [Source Manifest](source-manifest.md) — `manifest.sqlite` must exist before stats can run.
- `stats.json` is recomputed from the current manifest on each run (a cheap SQL aggregation), so it always reflects the latest manifest.

## Open Questions

- What additional statistics should be computed? Candidates:
  - ~~Total size in bytes~~ — implemented
  - ~~File type breakdown (by extension)~~ — implemented
  - ~~Duplicate count (files sharing the same MD5)~~ — now trivial from the manifest (`GROUP BY checksum`)
  - Date range (earliest/latest), from the manifest's `mtime` feature
- Should cross-project aggregate stats be generated?
