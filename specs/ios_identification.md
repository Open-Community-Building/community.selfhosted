# Device Info

## Purpose

Report the identity and health of a connected iOS device over USB, so devices can
be catalogued and troubleshooting/inventory has the facts: which iPhone/iPad it is,
its iOS build, storage and battery.

This is the iOS specialisation of [Location Identity](location_identity.md) — the
`UniqueDeviceID` it reads is the **strong identifier** for `device`-medium
locations, the same role `volume_uuid` plays for disks and `ssh_host_key_fingerprint`
plays for cloud objects. The existing `source_UniqueDeviceID` field in iPhone/iPad
project `config.json` files predates that generalisation and is kept as the
backwards-compatibility path.

## Definitions

- **Lockdown identity** (`all_values`): the root-domain property dictionary returned
  during the lockdownd handshake.
- **Domain value**: a property set read from a named lockdown domain (e.g. battery,
  disk usage) that is *not* part of `all_values` and must be queried explicitly.

## Behavior

### Connection

1. Connect to the first iOS device reachable over USB (usbmux).

### Identity

1. Read the device's `all_values` identity dictionary.
2. Print the grouped fields, when present: model, firmware, identifiers, cellular,
   state.
3. Print the convenience values: udid, product type, iOS version.

### Health & storage

1. Read the battery domain (`com.apple.mobile.battery`) and print it.
2. Read the disk-usage domain (`com.apple.disk_usage`) and print it, **excluding
   opaque binary blobs** — e.g. `NANDInfo`, a multi-KB raw NAND-geometry dump that
   is not human-readable, floods output, and is not JSON-serializable.

## Inputs

- A single iOS device connected over USB and paired/trusted.

## Outputs

- A human-readable summary printed to stdout. No files are written.

## Constraints

- Read-only: the device is queried, nothing is written to it.
- Binary/opaque domain values (e.g. `NANDInfo`) are excluded from the output.

## Open Questions

- Should the identity be persisted to `<identification_folder>/info.json` (a path the
  project registry already defines) instead of only printed?
- Should it select a device by `UniqueDeviceID` (matching a project's
  `source_UniqueDeviceID`, as `ios_file_stat.py` does) rather than always the first
  USB device?
