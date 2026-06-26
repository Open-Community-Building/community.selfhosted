# Git Logs

## Purpose

Convert the commit history of one or more local git repositories into SQLite for
exploration in Datasette — **append-only, with fixity** — so a queryable record of
who changed what, when, is kept across runs, and any **history rewrite**
(force-push / rebase) is detected.

## Definitions

- **Repository**: a local git working tree, read with `git log`.
- **Commit**: one entry in a repo's history — sha, author/committer identity and
  dates, parent shas, subject, body, change stats. The **sha is content-addressed**,
  so it doubles as the commit's fixity value.
- **Commit file**: one file changed in a commit (insertions/deletions, `--numstat`).
- **Ingest**: one run, recording which commits each repo's history contained then.
- **History rewrite**: a commit (sha) present in an earlier ingest and absent now —
  the signature of a force-push / rebase / amend.

## Behavior

### Repository selection

1. Process each project whose `source` is `Git Logs`.
2. Repositories come from the config — `repos` if present, otherwise
   `secondary_storage` (a path or a list). One project may cover many repositories;
   no per-repo folder is required.

### Extraction

1. For each repository, run `git log` over all history, reading per commit: sha,
   author/committer identity + ISO dates, parent shas, subject, body, and the
   `--numstat` file changes. Each row is tagged with `repo`.
2. A repository with no commits, or that cannot be read, is skipped with a warning.

### Ingest history (append-only)

1. The database is **never recreated**. Each run records an `ingests` row and, for
   every commit observed, a `commit_presence` row tying that commit to the ingest.
2. Because a commit is **content-addressed**, it is stored **once** in `commits`
   (and its files once in `commit_files`) and never overwritten. A commit that later
   disappears from history stays in `commits` — the rewritten-away history is kept.

### Fixity check (rewrite detection)

1. Compare the two most recent ingests' `commit_presence`, per repository:
   - **added** — shas present now, not before (normal growth).
   - **dropped** — shas present before, gone now → a **history rewrite**.
2. Each run ends with a report: per repo, `+added / −dropped`, listing any dropped
   shas and flagging the repo as rewritten. (There is no "content changed" class — a
   commit's sha *is* its content; a changed commit is a drop plus an add.)

### Work-hours report

1. At the end of every run, print a per-day breakdown of the current history
   (`commits_latest`): for each calendar day with commits — weekday, commit count,
   the active time window (first–last), the hours touched, and the repositories —
   in author-local time. This is the "when is it visible I worked" view.

## Inputs

- A `Git Logs` project whose config lists one or more local repository paths.

## Outputs

- `<project_folder>/git.sqlite` with:
  - `commits` (pk `(repo, sha)`) — every commit ever observed, retained.
  - `commit_files` — files changed per commit.
  - `ingests` — one row per run.
  - `commit_presence` (pk `(ingest_id, repo, sha)`) — which commits each ingest saw.
  - `commits_latest` — a view of the commits the latest ingest observed (current history).
  - `commits_fts` — FTS over subject / body / author.
- A printed **per-day work-hours report** (date, weekday, commits, time window, hours, repos).

## Constraints

- Read-only on the repositories — only `git log` is run.
- Append-only: ingests are never overwritten, so history stays comparable and
  rewritten-away commits are retained.
- Standard `git` CLI only; SQLite plumbing via sqlite-utils.
- Multiple repositories per project; rows namespaced by `repo`.

## Open Questions

- Retention: keep every commit forever (current), or prune those absent from the
  last N ingests?
- Include merge commits and branch/tag refs, or first-parent main-line only?
- Should the report distinguish a **rebase** (drops + adds) from a pure history
  **truncation** (drops only)?
- Split `parents` into a join table?
