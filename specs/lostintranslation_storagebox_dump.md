# LostInTranslation Storage Box Dump

## Purpose

The `LostInTranslation` iOS/Mac app writes its own data straight to the Hetzner
Storage Box (StorageBoxKit, over SFTP) — every person/group shard's translations and
voice recordings, and, since 2026-07-29, the AI Coach's own permanent call log (every
Soundness Check request/response, `specs/ai-coach-call-log.md` in the
`lostintranslation` repo). None of that ever passes through this project's own
`config.json`-driven pipeline the way, say, a Claude export does — the app is its own
uploader. This stage closes the loop: pull that data back down into
`projects/lostintranslation/fetched/`, the same "any other script" shape every other
project here already uses, so it's locally browsable, `git`/`datasette`-adjacent-
tool-friendly, and eligible for this project's own further processing later (fixity,
analysis) without needing the app or the phone/Mac it runs on.

## Definitions

- **Base**: one top-level folder on the Storage Box, named for a `lostintranslation`
  storage identity — a person/group shard's entity id (`1-` / `n-` prefixed,
  `specs/context.md` in the `lostintranslation` repo) or the AI Coach's own `a-coach`
  identity (`specs/ai-coach-call-log.md`). Each base holds a `<base>/LostInTranslation/`
  folder — the app's own `project` name in its `StorageBoxStore` addressing.
- **Declared bases**: the list of bases this stage pulls, named explicitly in
  `storage_box_bases` in the project's `config.json` — declared, not auto-discovered
  from an SFTP directory listing, matching this whole system's standing rule that a
  mount/source is a configuration fact, not a guess (`specs/locations.md` Constraints).

## Behavior

1. Runs over every project whose `source` is `LostInTranslation` (today, just
   `lostintranslation` itself) — same per-stage source filter every other command here
   uses (`specs/configure_projects.md`).
2. Reads `storage_box_bases` (a list of base ids) from the project's `config.json`.
3. For each declared base, appends the app's own fixed `/LostInTranslation` suffix
   (so `config.json` only names bases, never repeats the suffix).
4. Reads `storage_box_auth` (`"ssh_key"`, the default, or `"password"`) to pick a
   transport:
   - `"ssh_key"`: reads `storage_box_ssh_alias` (defaults to
     `storage-box-subaccount-selfhosted` — the same subaccount `hetzner_self_storagebox`
     already uses; confirmed 2026-07-29 that LostInTranslation's own Backup panel is
     configured against that exact subaccount, not a separate one) and delegates to
     `community.storagebox_dump.dump_bases`.
   - `"password"`: reads `storage_box_host`/`storage_box_username`/`storage_box_port`
     (none secret — added 2026-07-29 once the SSH key for that subaccount turned out
     not to be registered server-side yet, per `ssh -v` diagnosis: the key was offered
     and rejected, falling through to password) and delegates to
     `community.storagebox_dump.dump_bases_sftp`. The password itself never appears in
     `config.json` or this script — it is resolved from the macOS Keychain inside
     `storagebox_dump`, set once via `python -m storagebox_dump --host ... --username
     ... --set-password` (run by hand, on the machine that will run the dump; never
     passed through this pipeline).
   A project missing the fields its selected `storage_box_auth` needs is skipped with
   an error and a non-zero exit code, not a silent partial run.
5. Either transport lands each base at `fetched/<base>/LostInTranslation/`.
4. A project with no `storage_box_bases` declared is skipped with a warning, not a
   silent no-op — the same "a missing declaration is a fact to surface, not to guess
   past" discipline as everywhere else in this repo.
5. Incremental, idempotent, safe to re-run on a schedule — inherited directly from
   `storagebox_dump`'s own behavior (its spec's Behavior step 3); this stage adds no
   extra state of its own.

## Inputs

- `lostintranslation/config.json`'s `storage_box_bases` (required) and
  `storage_box_auth` (optional, defaults to `"ssh_key"`).
- If `storage_box_auth` is `"ssh_key"`: `storage_box_ssh_alias` (optional, defaulted).
- If `storage_box_auth` is `"password"`: `storage_box_host`, `storage_box_username`
  (both required), `storage_box_port` (optional, defaults to `23`) — plus a password
  already saved to the macOS Keychain via `python -m storagebox_dump --set-password`
  (a one-time, by-hand step; not this stage's concern).
- The `storagebox_dump` package (`pip install -e ../community.storagebox_dump`).

## Outputs

- `projects/lostintranslation/fetched/<base>/LostInTranslation/…` — one continuously
  synced mirror per declared base, matching the app's own remote layout exactly (a
  base's `Translations/`, `Recordings/`, or — for `a-coach` — `Calls/`, each further
  bucketed `YYYY/MM/DD/`, unchanged from how the app itself lays them out).

## Constraints

- Never creates or edits a `~/selfhosted/locations/` entry itself — `sources:
  ["hetzner_self_storagebox"]` in `config.json` references the **existing** location.
  **A new, separate `locations/lostintranslation/` entry was deliberately not
  created** even though an empty placeholder folder existed at that path before this
  spec: confirmed 2026-07-29 that the app's own subaccount is the identical
  `storage-box-subaccount-selfhosted` subaccount, and `specs/locations.md` explicitly
  treats "the subaccount is a delivery detail, not a separate site" — the
  `openheidelberg_hdd`/`maik_backup2026_hdd` merge (same spec, Open Questions,
  resolved 2026-07-20) is exactly the double-counting mistake a second location entry
  here would repeat, this time for 3-2-1-1-0 `copies`/`media` counts rather than
  partitions. The empty placeholder folder is left untouched (not this stage's data
  to delete) but is not wired into anything.
- Never touches `archive_targets` — that key is this project's own **meta**-backup
  (the `projects/lostintranslation/` working folder itself, pushed to the box under
  `selfhosted/projects/lostintranslation/`), an entirely separate concern from the
  app's own uploads this stage pulls down. The two must not be confused: this stage
  reads `sources`/`storage_box_bases`, never `archive_targets`.
- Read-only against the Storage Box (a pull), never deletes or modifies anything
  remote.

## Open Questions

- **Real base list unconfirmed beyond two entries.** `storage_box_bases` defaults to
  `["1-mkrdr", "a-coach"]` — `1-mkrdr` is `EntityStore.defaultSelfID` (always present),
  `a-coach` is the Coach's own identity (always present once the call-log feature is
  in real use). Any *other* real shard Maik has actually created (e.g. a family group)
  isn't guessable from the `lostintranslation` repo's code alone (`n-rdrfmly` appears
  there only as an illustrative example, not a confirmed real entity id) — he should
  extend this list himself if more shards exist.
- **Fixity/verification** is out of scope here, same open question
  `storagebox-dump.md` already names — this stage doesn't run `md5`/`manifest` against
  what it pulls.
