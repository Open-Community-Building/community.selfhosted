# community.selfhosted

A self-hosted, open-source preservation system for individuals and communities who
want to keep their own custody. Apply OAIS-style ingest, BagIt-shaped manifests,
PREMIS-aligned events, and 3-2-1-1-0 compliance — then disseminate to audiences
that scale from individual through project to public.

The companion **community.memex** package turns personal exports (Claude
conversations, Gmail Takeout) into SQLite for exploration in Datasette — one of
the source-importers that feed this archive.

Built using **Spec Driven Development (SDD)** — specifications are written first, implementation follows from specs.

## What is SDD?

Spec Driven Development puts specifications at the center of the development workflow:

1. **Spec first** — Every feature begins as a specification describing *what* the system does, not *how*.
2. **Review the spec** — Specs are reviewed and agreed upon before any code is written.
3. **Implement from spec** — Code is written to satisfy the specification.
4. **Validate against spec** — Tests verify the implementation matches the spec.

Specs live in the `specs/` directory and are the source of truth for system behavior.

## Specs

| Spec                                             | Status | Description                                                                                                                                    |
|--------------------------------------------------|--------|------------------------------------------------------------------------------------------------------------------------------------------------|
| [Configure Projects](specs/configure_projects.md) | Live | Declare project configuration in `config.cfg`, resolved by spaCy's config system                                                               |
| [Device Dump](specs/ios_file_stat.md)            | Draft | Dump file stats from iOS devices                                                                                                               |
| [Device Info](specs/ios_identification.md)       | Draft | Report a connected iOS device's identity, firmware, battery and storage                                                                        |
| [Photo Registry](specs/photo-registry.md)        | Draft | Discover and catalog photo projects from configured sources                                                                                    |
| [MD5 Checksums](specs/md5-checksums.md)          | Draft | Compute and store MD5 checksums for duplicate detection                                                                                        |
| [Stats](specs/stats.md)                          | Draft | Generate per-project and cross-project statistics                                                                                              |
| [Source Manifest](specs/source-manifest.md)      | Draft | Per-source index of every item — locator + checksum + features — for sampling, cross-source dedup, stats and parallelism                       |
| [Git Logs](specs/git-logs.md)                    | Draft | Convert local git repositories' commit history (commits + file changes) to SQLite, keyed by repo                                               |
| [Fixity & Change Detection](specs/fixity.md)     | Draft | Detect additions / losses / silent content changes across ingests by comparing checksums (fixity checking)                                     |
| [Claude Web Ingest](specs/claude_web_ingest.md)  | Draft | Unpack new Claude export zips from claude_web_ingest/ into UTC-named fetched/ snapshots (only conversations.json)                      |
| [Claude Web](specs/claude_web.md)         | Draft | Convert the latest Claude snapshot to SQLite and record the conversations.json SHA-256 provenance                                              |
| [Locations](specs/locations.md)                  | Live | Registry of storage locations with copy role / medium / site / online state — 3-2-1-1-0 evaluated per project                                  |
| [Location Identity](specs/location_identity.md)  | Draft | Per-medium hardware identification (Volume UUID / iOS UDID / SSH host key) — fixity for the storage container, generalising the iOS UDID match |
| [Dissemination](specs/dissemination.md)          | Draft | Build per-audience DIPs (self/family/friends/project/public) as BagIt bags, deliver via SFTP to Hetzner Storage Box subaccounts                |

## Project Structure

```
community.selfhosted/
├── specs/                # Specifications — source of truth
│
├── project.yml           # Weasel / spaCy-projects workflow: commands + pipelines
├── config.cfg            # Declarative configuration (projects root), resolved by spaCy's config system
├── requirements.txt      # Pinned runtime deps (sqlite-utils, spaCy/weasel, datasette, pymobiledevice3)
├── project_registry.py   # Registered project discovery + load_projects() / ensure_dirs() (used by every script)
│
│                         # Photo inventory pipeline (runs over every configured project)
├── photos_md5.py         # MD5 + size checksums            → md5.json
├── photos_metadata.py    # Attach Google Takeout metadata   → metadata.json
├── photos_stats.py       # Counts / sizes / type breakdown  → stats.json
│
│                         # Source Manifest + fixity (append-only ingests, SHA-256, change detection)
├── manifest.py           # Generic manifest engine: build / fixity_check / fixity_events
├── photos_manifest.py    # Photos item-iterator             → photos_manifest/manifest.sqlite
│
│                         # iOS device acquisition (pymobiledevice3, over USB)
├── ios_identification.py # Print device identity / battery / disk
├── ios_file_stat.py      # AFC-walk a device                → dump/pymobiledevice3_files.json
│
│                         # Archive → SQLite (for Datasette)
├── claude_web_ingest.py      # Unpack Claude export zips → fetched/<utc>/conversations.json
├── claude_web.py     # Latest Claude snapshot    → conversations.sqlite (+ SHA-256)
├── gmail_sqlite.py       # Google Takeout mbox       → gmail.sqlite (via memex)
└── git_logs.py           # Git commit history        → git.sqlite (append-only; flags rewrites)
```

## Getting Started

Photo projects live under `~/selfhosted/photos/projects/`; each folder has a
`config.json` describing its source. The projects root is declared in
[`config.cfg`](config.cfg) and resolved through spaCy's config system — see
[Configure Projects](specs/configure_projects.md).

> The `gmail_sqlite` command delegates to the companion **community.memex** package.
> Install it into the same environment — `pip install -e ../community.memex`

```bash
source ~/selfhosted/.venv/bin/activate
cd ~/selfhosted/community.selfhosted
pip install -r requirements.txt   # first-time setup: sqlite-utils, spaCy/weasel, datasette, pymobiledevice3

# Run the whole photo pipeline (ensure_dirs → md5 → manifest → metadata → stats):
weasel run photos
# …or the Claude pipeline (ingest new claude_web_ingest → convert latest → SQLite):
weasel run claude

# …or run any single command — `weasel run <name>` and `spacy project run <name>`
# are equivalent:
spacy project run resolve_config  # discover & print the configured projects
spacy project run ensure_dirs     # create each project's fetched/ & processed/ dirs
spacy project run compliance      # per-project 3-2-1-1-0 status (read-only)
spacy project run device_info     # print a connected iOS device's identity, battery, disk
spacy project run device_files    # dump file stats from a connected iOS device (AFC)
spacy project run md5             # MD5 + size checksum every fetched file
spacy project run manifest        # ingest → Source Manifest (locator + checksum + features) + fixity report
spacy project run metadata        # attach Google Takeout metadata (run after md5)
spacy project run stats           # counts / sizes / type breakdown (run after md5)
spacy project run gmail_sqlite    # Google Takeout mbox → SQLite via `memex`
spacy project run claude_web_ingest   # unpack new Claude export zips: claude_web_ingest/ → fetched/<utc>/conversations.json
spacy project run claude_web  # convert the latest Claude snapshot → conversations.sqlite (+ SHA-256 provenance)
```

### Restrict to one project

Any stage (and the `photos` / `claude` workflows) accepts a project selector — useful
when you want to run a pipeline against a single project rather than every configured
one. See [Configure Projects](specs/configure_projects.md#project-selection).

```bash
# Direct (script): `--project` / `-p`
python claude_web.py --project claude_web

# Via weasel (can't forward args): use the PROJECT env var
PROJECT=googlephotos_takeout weasel run manifest
PROJECT=claude_web weasel run claude             # whole workflow, one project
spacy project run git_logs        # git commit history → SQLite (append-only; flags history rewrites)
```
