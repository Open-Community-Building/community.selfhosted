# MD5 Fingerprinting

## Purpose

Compute MD5 checksums for every photo in a project to enable duplicate detection and data integrity verification across systems.

## Definitions

- **Fingerprint**: The MD5 hash of a file's contents.
- **Fingerprint index**: A JSON file (`md5.json`) mapping file paths to their metadata and checksums.

## Behavior

### Processing

1. For each photo project, check if `md5.json` already exists in the processed directory.
2. If `md5.json` exists, skip the project (already processed).
3. If not, walk the project's `fetched_folder` recursively.
4. For each file (excluding `.DS_Store`):
   - Read the file contents and compute the MD5 hash.
   - Record the file's absolute path, filename, MD5 checksum, and file size in bytes.
5. Write the complete fingerprint index to `md5.json`.

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

- `<processed_folder>/md5.json` — the fingerprint index for the project.

## Constraints

- `.DS_Store` files are excluded.
- Processing is idempotent — if `md5.json` exists, the project is skipped entirely.
- The JSON output is pretty-printed with 4-space indent, sorted keys, and non-ASCII characters preserved.

## Open Questions

- Should re-processing be supported (e.g., when new files are added to a project)?
- Should the hash algorithm be configurable (e.g., SHA-256 for stronger integrity guarantees)?
- Should file type filtering go beyond `.DS_Store` exclusion?
