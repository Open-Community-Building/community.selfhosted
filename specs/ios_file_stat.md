# Device Dump

## Purpose

Acquire a file-stat inventory of a connected iOS device over USB, so a device's
contents can be catalogued and analysed — and later folded into the
[Source Manifest](source-manifest.md) — without copying the files off the device.

## Definitions

- **Device**: an iPhone or iPad connected over USB and paired/trusted.
- **AFC** (Apple File Conduit): the `pymobiledevice3` service used to walk and
  `stat` the device's filesystem over USB.
- **Dump**: the output file `dump/pymobiledevice3_files.json` — a JSON object
  mapping each device file path to its stats.
- **Kind**: a coarse type derived from a file's extension — `image` (`.heic`,
  `.jpg`, `.jpeg`, `.png`, `.dng`, `.gif`), `movie` (`.mov`, `.mp4`, `.m4v`), or
  `other`.

## Behavior

### Device selection

1. Connect to the iOS device reachable over USB (usbmux / lockdown).
2. Read the device's lockdown identity (`all_values`) and select the configured
   project whose `source` is `IPhone` or `IPad` and whose `source_UniqueDeviceID`
   matches the device's `UniqueDeviceID` — so the dump lands in the right project.
3. If that project's dump file already exists, skip (idempotent — do not re-dump).

### Walk & stat

1. Walk the device filesystem recursively over AFC, starting at `/`.
2. For each file, record:
   - `path` — the full device path.
   - `kind` — `image` / `movie` / `other`, by extension.
   - `size` — `st_size`, in bytes.
   - `ifmt` — `st_ifmt` (file mode / type flags).
   - `mtime`, `birthtime` — from `st_mtime` / `st_birthtime`, as timestamps.
3. Write the collected records to the dump file.

## Inputs

- A single iOS device connected over USB and trusted.
- A project whose `source` is `IPhone` or `IPad` and whose `source_UniqueDeviceID`
  matches the connected device.

## Outputs

- `<project>/dump/pymobiledevice3_files.json` — a JSON object keyed by device file
  path; each value is `{path, kind, size, ifmt, mtime, birthtime}` (datetimes
  written as ISO-8601, keys sorted, pretty-printed).

## Constraints

- **Read-only on the device** — files are walked and `stat`-ed, never modified or
  copied off.
- **Idempotent** — if the matched project's dump already exists, the run is skipped.
- The device is matched to its project by `UniqueDeviceID`.

## Open Questions

- Should the dump feed the [Source Manifest](source-manifest.md) directly — each
  device file an item, `path` as the locator and `size`/`mtime`/`kind` as features?
  AFC files can't be cheaply checksummed over USB, so this needs the
  checksum-optional item the manifest spec raises.
- The script writes JSON, but its stated aim ("exploration in Datasette") points at
  SQLite — should it emit a manifest (SQLite) instead?
- Should re-dumping be supported (currently an existing dump is skipped)?
