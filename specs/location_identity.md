# Location Identity

## Purpose

Tell **which physical medium** a mounted/connected location really is, so an
external HDD plugged into a different USB port — or a backup disc whose label
collides with another (`openheidelberg`, `openheidelberg 1`) — can never be
mistaken for the location it isn't. Generalises the existing iOS `UniqueDeviceID`
match (used by [Device Info](ios_identification.md) and Device Dump to bind a
connected iPhone/iPad to its project) into a per-medium scheme that applies to
disks and cloud objects too: read a stable identifier set from the medium, store
it on the location, verify at mount time.

This is **fixity for the storage container**, complementing the
[content fixity](fixity.md) already on the data inside. Both must hold before a
stage trusts data on a mount as the data it claims to be.

## Definitions

- **Identifier**: a value that uniquely identifies a physical storage medium and
  survives common operations (remount, rename, USB-port move). Examples: APFS
  Volume UUID, disk media serial, iOS UDID, a stable subaccount hostname.
- **Strong identifier**: an identifier that verification keys on. A medium may
  have **one or more** — disks have two (`volume_uuid` *and* `media_serial`) so
  identity survives either a reformat (keeps `media_serial`) or an enclosure
  swap (keeps `volume_uuid`). A match on **any** strong identifier confirms
  identity.
- **Identification**: the extraction step that reads identifiers from a live,
  mounted/connected medium and records them.
- **Verification**: matching freshly-read identifiers against the location's
  recorded ones — confirming "this mount is the location I think it is."
- **Identity drift**: a mounted medium whose identifiers don't match the
  location it was bound to — the container-level equivalent of a fixity failure.

## Behavior

### Per-medium identifier sets

For each `medium` (the closed enum in [Locations](locations.md)), a small **closed
set** of identifiers is read:

| medium | strong identifier(s) | supporting | source |
|---|---|---|---|
| `internal_ssd` / `external_ssd` / `external_hdd` (APFS on macOS) | `volume_uuid`, `media_serial` | `disk_uuid`, `volume_name` | `diskutil info -plist <mount_point>` |
| `device` (iPhone / iPad) | `unique_device_id` (iOS UDID) | `serial_number`, `unique_chip_id` (ECID), `product_type` | `pymobiledevice3` lockdown handshake (the existing [Device Info](ios_identification.md) call) |
| `cloud_object` (Hetzner Storage Box, S3, …) | `host` (the stable subaccount URL — e.g. `u573272-sub1.your-storagebox.de`) | — | declared in `location.json` (no extractor — the URL itself is the identity) |
| `optical` / `tape` | `medium_label` + per-disc serial when present | — | best-effort |
| `other` | `volume_uuid`, `media_serial` | `disk_uuid`, `volume_name` | `diskutil info -plist <mount_point>` + USB `ioreg` serial lookup (`diskutil_other`, same probe as the APFS media, deliberately filesystem-agnostic) |

**Real gap closed (2026-07-24):** `other` was declared in the medium enum from the
start but had no registered extractor at all, so any project opting into hardware
verification for an `other`-medium location would hit a hard `extraction_failed`
refuse on every single command — not the soft "no identity recorded yet" this
medium's free-form nature is supposed to produce. Built `extract_other()`, reusing
the same diskutil + USB-ioreg probe as APFS media (it was never actually
APFS-specific — `diskutil info -plist` works against any filesystem `diskutil`
recognizes, FAT/exFAT included; the strong identifiers just routinely come back
null for a bare card with no exposed hardware identity, which `identify()`/
`verify()` already treat as `no_identification`, not a failure). Verified for real
against a Samsung SD card whose own independent probe
(`community.sd_card_file_registry`) had already found Unknown/Unknown for serial
and model: `identify()` now establishes a real (if mostly-null) identification.json
instead of the project refusing to run at all.

`volume_name` for disks is **informational only** — it is exactly what collides
between same-named volumes, so it is never used for matching.

For disks, both strong identifiers are recorded; verification passes when **either**
matches — surviving a reformat (`media_serial` persists) *or* a USB-enclosure swap
(`volume_uuid` persists), but not both at once (that is a new medium).

### Identification (extract)

1. Each location grows a sibling file `~/selfhosted/locations/<id>/
   identification.json` — the *factual* identity, vs `location.json`'s declared
   metadata.
2. A medium-specific extractor knows how to read identifiers from the live mount:
   - macOS APFS volumes — parse `diskutil info -plist`.
   - iOS devices — the existing `lockdown.all_values` read.
   - Cloud objects — no extractor; the strong identifier (`host`) is declared in
     `location.json` and copied into `identification.json` for shape uniformity.
3. The first-time identification creates `identification.json` from scratch and
   prints `establishing identity for <id>`. **Real gap closed (2026-07-24):**
   `weasel run verify_identity` previously only ever called `verify()` (reads an
   existing file, never creates one) for every registered location — so a
   freshly registered location had no CLI path to actually get identified at
   all, only an ad-hoc one-off script. `main()` now checks each location for a
   missing `identification.json` first and calls `identify()` instead in that
   case, so registering a brand-new location and running
   `weasel run verify_identity` (with its medium mounted/connected) is now
   sufficient on its own to establish it for real.
4. **Re-identification**: when run again, the new read is accepted only if **at
   least one** recorded strong identifier still matches; the file is then
   overwritten with the fresh read (so non-strong fields can update). All
   strong identifiers mismatching is **identity drift** — the file is left
   untouched and the alarm fires.

### Verification (check before use)

1. Before any stage uses a location's `mount_point`, the system reads the live
   medium's strong identifiers and compares them to the recorded ones.
2. **Any strong identifier matches** → proceed silently; a `verified_identity`
   event is recorded per use.
3. **All strong identifiers mismatch** → loud refuse: the stage exits with an
   `identity drift` error naming the expected location, the recorded strong
   identifiers, and the values found. The stage does **not** silently fall back
   to another location.
4. **Missing `identification.json`** → first-run: extract, record, proceed with a
   one-line notice. (Skippable with `--skip-identity` for genuine first
   installation only; never silent.)

### Migration from the existing iOS scheme

The current `source_UniqueDeviceID` in iPhone/iPad project `config.json` files is
the iOS specialisation that predates this generalisation. Migration: extract the
UDID into a registered location's `identification.json`, register the location,
and update the project's `archive_targets` to point at it; the
`source_UniqueDeviceID` field is then **removed** from `config.json`. **There is
no runtime fallback** — a `device`-medium archive target must have a registered
location identity before its stage will run.

## Inputs

- A registered location with a `mount_point` (or a connected device, or a
  declared cloud `host`).
- The medium-specific extractor (`diskutil`, `pymobiledevice3`); cloud uses the
  declared URL with no separate extraction.

## Outputs

- `~/selfhosted/locations/<id>/identification.json` — `{identifiers: {…},
  recorded_at, extractor}`.
- A `verified_identity` event in `~/selfhosted/archive/archive.sqlite/events`
  emitted **per use** (one row per stage run × location used) — honest provenance,
  at the cost of a slightly chatty ledger.
- A loud **identity drift** error on mismatch — no event recorded; the alarm is
  the response.

## Constraints

- The strong identifier per medium is fixed by this spec; downgrades require a
  spec change.
- A location id is permanent. If a medium fails and is replaced, the replacement
  is a **new** location (acquisition + new identification). The decommissioned
  location's identification stays on file as chain of custody.
- Verification is cheap (one `diskutil` or lockdown call) and **not skippable**
  on regular runs — refusing to skip it is the whole point.
- This identity check operates on the **container**; content fixity in
  [fixity.md](fixity.md) operates on the data inside. Both must pass before a
  stage trusts the mount.

## Open Questions

- When a disk has one strong identifier matching and the other changed (e.g.
  `volume_uuid` same, `media_serial` changed), should the system *warn* in
  addition to passing? The verification policy says "either matches → pass," but
  a partial match is genuinely interesting — it points at a legitimate
  enclosure-swap or reformat that may warrant a follow-up event.
- Should `identification.json` keep a *history* of past strong-identifier values
  (so a legitimate `media_serial` change after a reformat shows up as an
  audit-trail entry rather than just silently overwriting)?
