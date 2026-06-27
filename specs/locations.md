# Locations

## Purpose

Register the physical/logical storage homes that hold project data — and let the
**3-2-1-1-0** backup strategy be evaluated, **per project**, as a SQL query rather
than a hand-counted spreadsheet.

A location is the archival "where the bits live" — promoting the bare
`primary_storage` / `secondary_storage` paths that today sit inside each project's
`config.json` into a first-class registry with its own description, lifecycle, copy
role, and verification state.

## Definitions

- **Location**: one storage home holding bits — an internal SSD, an external HDD, a
  cloud object store, an attached device, an offline disk in a drawer. Maps to
  PREMIS *storage* + a free-text custodial history.
- **Copy**: one instance of a project's data at one location. A project may have
  many copies, each at a different location; the 3-2-1-1-0 strategy is evaluated
  over the set of *active* copies.
- **3-2-1-1-0**: the gold-standard backup strategy — **3** copies on **2** distinct
  media, **1** off-site, **1** offline (or immutable), with **0** errors after
  fixity verification.
- **Source link**: an entry tying a project to a location at a point in time
  (`status` ∈ active / migrated / retired). Locations may come and go; the
  project's chain of custody is the timeline of its source links.
- **Active location**: one with no terminal lifecycle event (decommissioned,
  deaccessioned).
- **Home site**: the `site` identifier this project treats as on-site; declared
  per project in its `config.json` (`home_site: <string>`). Anything not matching
  it counts toward the **off-site** check.

## Behavior

### Location registry

1. Locations are declared one per directory under `~/selfhosted/locations/`, each
   with a `location.json` carrying:
   - `id` (folder name, stable, never renamed)
   - `medium` — **closed enum**: `internal_ssd` / `external_hdd` / `external_ssd`
     / `cloud_object` / `optical` / `tape` / `device` / `other`. Closed so the
     "distinct media" count (the "**2**" leg) stays reliable; extending the set
     is a spec change.
   - `site` — a free-text site identifier (`home`, `hetzner_storage_box`,
     `friend_basement`, …) for the **off-site** check
   - `online_state` — `online` / `offline` / `immutable`, for the **offline /
     immutable** check
   - `mount_point` — declared path where the bits are accessible when online
     (not auto-discovered from `/Volumes`; declared so a missing mount surfaces
     as a configuration fact, not a guess)
   - `capacity_bytes` — optional
   - `acquired_at` — when the medium entered service
   - `history` — free-text custodial history (origin, transfers, why it exists)
   - `access_tier` — see [Dissemination](dissemination.md); constrains which
     audiences any project drawing from this location may serve
   - `ssh_alias` — optional, **cloud_object only**: the `~/.ssh/config` Host
     alias the system uses to reach this location (so credentials, port, and
     identity file live in the SSH config). When present, compliance probes the
     remote via SFTP (`echo "cd <path>" | sftp -b - <alias>`) to verify
     materialisation. Without it, cloud targets show as not materialised because
     the local `Path.exists()` check is structurally blind to SFTP-accessed
     paths.
2. Discovery mirrors the project registry: walk the directory, read each
   `location.json`, build a registry keyed by `id`. `project_registry.select_*` style.
3. A location's directory also holds a sibling `identification.json` — the
   factual hardware identity (volume UUID, iOS UDID, SSH host key, etc.) — used
   to verify "this mount is the location I think it is" before any stage trusts
   the data on it. See [Location Identity](location_identity.md). The
   `mount_point` declared in `location.json` becomes binding only via this
   verification check; mount_point + volume name alone are not trustworthy
   (USB volumes with colliding names mount in arbitrary order).

### Per-project source links

1. A project's `config.json` carries `sources: [<location_id>, …]` — the active
   source locations the project draws from. Bare `primary_storage` /
   `secondary_storage` paths remain accepted (resolved against the matching
   location's `mount_point`) so existing projects keep working.
2. A project MAY add `archive_targets: [{location: <id>, path: <relative_path>}, …]`
   — locations that hold the project's archived copies (vs the live source), each
   entry naming the location and the path of the project's data **relative to
   that location's `mount_point`**. One location can therefore hold copies of
   many projects at distinct subpaths. This is what makes 3-2-1-1-0 evaluable:
   compliance counts archive targets, not the (typically single) live source.
3. A project's `config.json` carries `home_site: <string>` — the `site`
   identifier treated as on-site for the **off-site** compliance check. Declared
   per project (not globally) so different installs / collaborators can each
   call their own home "home".
4. The full source/target *history* of a project is in the Events ledger (below);
   `config.json` carries the *current* state.

### Lifecycle events

The location registry is timeless on its own; lifecycle is captured in an
append-only events ledger at `~/selfhosted/archive/archive.sqlite` (the first
cross-project SQLite — sibling of `photos/`, `locations/`, `story/`), table
`events`:

1. Event kinds: `acquired`, `mounted`, `migrated`, `verified`, `decommissioned`,
   `deaccessioned`, `restored`, `disseminated` (the last is for
   [Dissemination](dissemination.md)).
2. Each event records `(when, kind, agent, location_id, project_id?, notes)`.
   `agent` is the human or tool responsible (PREMIS *Agent*).
3. The **`verified`** event records the outcome of a fixity run against a location
   — this is the "0 errors" leg of 3-2-1-1-0. The existing `manifest.fixity_events`
   table is its detailed counterpart; `events.verified` is the summary row.

### Per-project compliance check

For each project P, count over its `archive_targets` whose locations are currently
**active** (no terminal event):

1. `copies` = number of distinct active locations
2. `media` = number of distinct `medium` values
3. `offsite` = at least one location whose `site` ≠ the project's `home_site`
4. `offline` = at least one location whose `online_state` ∈ {`offline`, `immutable`}
5. `all_verified` = every active location has a `verified` event within the
   freshness window (**90 days**)
6. If the project has no active `archive_targets` (or `copies = 0`), the result
   is **not yet evaluable**, not "non-compliant" — it is the unattempted state.
   This is precisely the alarm 3-2-1-1-0 is meant to raise: "you have no
   archive copies."

P is otherwise **compliant** when `copies ≥ 3 AND media ≥ 2 AND offsite AND
offline AND all_verified`; falling short on any of those is **non-compliant**,
with the specific failing legs reported so it's actionable.

The reason compliance is **per project**, not per source location: source
locations come and go (the iPhone is sold, a download volume is shucked, a Storage
Box is migrated). Projects remain. A project's data has a lifetime measured in
decades; a medium's lifetime in years. Compliance is therefore a property of the
project, with locations the means by which it's met.

## Inputs

- `~/selfhosted/locations/<id>/location.json` per location.
- Each project's `config.json`: `sources` / `archive_targets` referencing
  location ids, plus `home_site`.
- The events ledger (`~/selfhosted/archive/archive.sqlite`, table `events`).

## Outputs

- A queryable registry of locations and links.
- For each project, a compliance row: `(project_id, copies, media, offsite,
  offline, all_verified, status)` where `status` ∈ `compliant` /
  `non_compliant` / `not_yet_evaluable`, with the specific failing legs named
  when `non_compliant`.
- A finding-aid view in Datasette joining manifest items → location → project →
  events, so for any item you can answer "which copies hold it, when were they
  last verified, when was the location acquired."

## Constraints

- Location ids are stable; renaming a location is a `deaccession` + new
  `acquisition`, not an edit.
- The events ledger lives at `~/selfhosted/archive/archive.sqlite` and is
  **append-only** — like the manifest, like git_logs.
- `medium` is a **closed enum**; extending it is a spec change so the "distinct
  media" count stays reliable.
- `mount_point` is **declared**, not auto-discovered — a missing mount surfaces
  as a configuration fact rather than a silent guess. Before any stage uses a
  declared `mount_point`, [Location Identity](location_identity.md) verifies the
  medium's strong identifier (volume UUID for disks, UDID for iOS devices,
  SSH host key fingerprint for cloud) matches the location's recorded one.
- The verification freshness window is **90 days** (global, not per-location or
  per-project — simpler and field-typical).
- Backwards compatible with the current `primary_storage` /
  `secondary_storage`: when those are present, they resolve to a location's
  `mount_point` if a matching location exists; otherwise the bare path keeps
  working.
- A location's `access_tier` constrains the audiences any project drawing from it
  may serve — see [Dissemination](dissemination.md).
- The Hetzner Storage Box (one box = one site) counts as **one** location's site
  regardless of how many subaccounts it hosts; the subaccount is a delivery
  detail, not a separate site for off-site purposes.

## Open Questions

- **Location granularity**: one location per *physical medium* (an external HDD
  with two partitions is one location) or per *mount-point* (each partition is
  its own)? Per-medium matches PREMIS *storage* most closely; per-mount-point is
  simpler to declare. Leaning per-medium.
- **`verified` event payload**: just `{status, when}`, or also a count of items
  re-checksummed and any failures? (Detail also lives in `manifest.fixity_events`,
  so this is a redundancy decision.)
- **Default `home_site`** when absent from a project's `config.json`: hardcoded
  `"home"`, or required (fail loudly)? Hardcoding lets existing projects keep
  working without edits; requiring it forces an intentional declaration.
