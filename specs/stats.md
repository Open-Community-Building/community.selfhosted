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

### Output Format

```json
{
  "total": 1234
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
  - Total size in bytes
  - File type breakdown (by extension)
  - Duplicate count (files sharing the same MD5)
  - Date range (earliest/latest file, if EXIF is extracted)
- Should cross-project aggregate stats be generated?
