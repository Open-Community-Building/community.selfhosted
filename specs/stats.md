# Stats

## Purpose

Generate statistics for each photo project to provide an overview of the inventory and support reporting across systems.

## Definitions

- **Stats file**: A JSON file (`stats.json`) containing computed statistics for a single project.

## Behavior

### Processing

1. For each photo project, check if `stats.json` already exists in the processed directory.
2. If `stats.json` exists, skip the project (already processed).
3. If not, read the project's `md5.json` fingerprint index.
4. Compute statistics and write them to `stats.json`.

### Computed Statistics

| Stat | Description |
|------|-------------|
| `total` | Total number of files in the fingerprint index |
| `total_size` | Sum of all file sizes in bytes |
| `total_size_human` | Human-readable representation of `total_size` (e.g., `"1.2 GB"`) |
| `types` | Object mapping lowercase file extensions to their count |

### Total Size

1. Sum the `size` field of every entry in the fingerprint index.
2. Store the raw byte count as `total_size`.
3. Convert to a human-readable string as `total_size_human` using binary units: B, KB, MB, GB, TB. Use one decimal place (e.g., `"1.2 GB"`, `"843.5 MB"`). Use the largest unit where the value is >= 1.

### File Type Breakdown

1. For each file in the fingerprint index, extract the file extension from the filename.
2. Normalize the extension to lowercase (e.g., `.JPG` becomes `.jpg`).
3. Files with no extension are counted under the key `""` (empty string).
4. Produce an object mapping each extension to its count, sorted by key.

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

- A project's `md5.json` fingerprint index (must exist before stats can be generated).

## Outputs

- `<processed_folder>/stats.json` — statistics for the project.

## Constraints

- Stats depend on MD5 fingerprinting — `md5.json` must exist before stats can run.
- Processing is idempotent — if `stats.json` exists, the project is skipped entirely.

## Open Questions

- What additional statistics should be computed? Candidates:
  - ~~Total size in bytes~~ — implemented
  - ~~File type breakdown (by extension)~~ — implemented
  - Duplicate count (files sharing the same MD5)
  - Date range (earliest/latest file, if EXIF is extracted)
- Should cross-project aggregate stats be generated?
