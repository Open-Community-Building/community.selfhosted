# Photo Discovery

## Purpose

Discover and catalog photo projects from configured sources so the system has a complete inventory of what exists and where.

## Definitions

- **Projects directory**: `~/selfhosted/photos/projects/`
- **Photo project**: A folder under the projects directory containing a `config.json` and a set of fetched photos.
- **Fetched directory**: A `fetched/` subfolder within each project, created automatically if missing.
- **Processed directory**: A `processed/` subfolder within each project, created automatically if missing.

## Behavior

### Project Discovery

1. Scan the projects directory for all subfolders (excluding hidden folders starting with `.`).
2. For each subfolder, read `config.json` from the folder root.
3. Register the project with:
   - `id` — the folder name
   - `project_folder` — absolute path to the project folder
   - `fetched_folder` — path to `<project_folder>/fetched/`
   - `processed_folder` — path to `<project_folder>/processed/`
   - `processed_md5` — path to `<processed_folder>/md5.json`
   - `processed_stats` — path to `<processed_folder>/stats.json`

### Fetched Directory

- If the `processed/` directory does not exist for a project, create it.

### Processed Directory

- If the `processed/` directory does not exist for a project, create it.

## Inputs

- Projects directory on the filesystem.
- A `config.json` file in each project folder.

## Outputs

- A dictionary of photo projects keyed by project ID, each containing paths and configuration.

## Constraints

- Hidden folders (prefixed with `.`) are excluded from discovery.
- A missing `config.json` is an error — the project is not silently skipped.

## Open Questions

- Should discovery support nested project structures?
- Should `config.json` have a required schema?
