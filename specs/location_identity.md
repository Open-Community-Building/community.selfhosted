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
  Volume UUID, iOS UDID, SSH host key fingerprint.
- **Identification**: the extraction step that reads identifiers from a live,
  mounted/connected medium and records them.
- **Verification**: matching freshly-read identifiers against the location's
  recorded ones — confirming "this mount is the location I think it is."
- **Identity drift**: a mounted medium whose identifiers don't match the
  location it was bound to — the container-level equivalent of a fixity failure.

## Behavior

### Per-medium identifier sets

For each `medium` (the closed enum in [Locations](locations.md)), a small **closed
set** of identifiers is read, in priority order (strongest first — the first one
is the **strong identifier** that verification keys on):

| medium | strong identifier | supporting | source |
|---|---|---|---|
| `internal_ssd` / `external_ssd` / `external_hdd` (APFS on macOS) | `volume_uuid` | `disk_uuid`, `media_serial`, `volume_name` | `diskutil info -plist <mount_point>` |
| `device` (iPhone / iPad) | `unique_device_id` (iOS UDID) | `serial_number`, `unique_chip_id` (ECID), `product_type` | `pymobiledevice3` lockdown handshake (the existing [Device Info](ios_identification.md) call) |
| `cloud_object` (Hetzner Storage Box, S3, …) | `ssh_host_key_fingerprint` (sha256) | `host` | `ssh-keyscan -t ed25519 <host>` |
| `optical` / `tape` | `medium_label` + per-disc serial when present | — | best-effort |
| `other` | free-form | — | declared by the operator |

`volume_name` for disks is **informational only** — it is exactly what collides
between same-named volumes, so it is never used for matching.

### Identification (extract)

1. Each location grows a sibling file `~/selfhosted/locations/<id>/
   identification.json` — the *factual* identity, vs `location.json`'s declared
   metadata.
2. A medium-specific extractor knows how to read identifiers from the live mount:
   - macOS APFS volumes — parse `diskutil info -plist`.
   - iOS devices — the existing `lockdown.all_values` read.
   - Cloud objects — `ssh-keyscan`.
3. The first-time identification creates `identification.json` from scratch and
   prints `establishing identity for <id>`.
4. **Re-identification**: when run again, the new read is accepted only if the
   recorded strong identifier still matches; the file is then overwritten with
   the fresh read (so non-strong fields can update). A strong-identifier mismatch
   is **identity drift** — the file is left untouched and the alarm fires.

### Verification (check before use)

1. Before any stage uses a location's `mount_point`, the system reads the live
   medium's strong identifier and compares it to the recorded one.
2. **Match** → proceed silently.
3. **Mismatch** → loud refuse: the stage exits with an `identity drift` error
   naming the expected location, the recorded strong identifier, and the value
   found. The stage does **not** silently fall back to another location.
4. **Missing `identification.json`** → first-run: extract, record, proceed with a
   one-line notice. (Skippable with `--skip-identity` for genuine first
   installation only; never silent.)

### Relationship to the existing iOS scheme

The current `source_UniqueDeviceID` in iPhone/iPad project `config.json` files is
the iOS specialisation that predates this generalisation. For backwards
compatibility, when a location's medium is `device` and `identification.json` is
missing, the verifier falls back to `source_UniqueDeviceID` on the matching
project's config. Migrating an iOS device to the new scheme means moving the UDID
out of the project's `config.json` into a registered location's
`identification.json` and pointing the project's `archive_targets` at it.

## Inputs

- A registered location with a `mount_point` (or a connected device).
- The medium-specific extractor (`diskutil`, `pymobiledevice3`, `ssh-keyscan`).

## Outputs

- `~/selfhosted/locations/<id>/identification.json` — `{identifiers: {…},
  recorded_at, extractor}`.
- A `verified_identity` event in `~/selfhosted/archive/archive.sqlite/events` per
  successful verification (cheap; one row per stage run × location used).
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

- Whether `media_serial` should be a **second** strong identifier alongside
  `volume_uuid` for disks, so a deliberate reformat is treated as identity drift
  (it would currently be: reformat changes `volume_uuid`). The cleaner reading:
  a reformat is itself a `migrated` event with a new identity — strong identifier
  stays `volume_uuid` alone.
- For cloud, SSH host-key rotation by the provider would look like identity
  drift. Allow a `replace-host-key` command (records a `migrated` event with the
  old + new fingerprints), or pin a known list shipped per Storage Box?
- The fallback to `source_UniqueDeviceID` from project config — keep it
  permanently (cheap), or sunset it once all iOS projects have registered
  location identities?
- Should `verified_identity` events be emitted per *use* (one per stage run × 
  location — could be many per day) or rate-limited (e.g. one per day per
  location)? Per-use is the most honest; rate-limited keeps the ledger lean.
