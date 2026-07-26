#!/usr/bin/env python3
"""
Location identity verification — see specs/location_identity.md.

For each medium type, a small extractor reads the live strong identifier(s) and
compares them to the location's recorded `identification.json`. Any strong
identifier matching → pass; all mismatching → loud refuse (identity drift).
This is "fixity for the storage container," complementing content fixity in
specs/fixity.md.

This module is consumed by pipeline stages as a silent precondition
(`verify_pipeline_location(project, locations)` — call before writing/reading)
and run directly as `weasel run verify_identity` for an ad-hoc registry sweep.

Set `SKIP_IDENTITY=1` to bypass the precondition (first-install only, never
silent in normal operation).
"""

import asyncio
import json
import os
import plistlib
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import archive_ledger
from project_registry import load_locations, select_locations

# Per-medium extractor dispatch. Closed enum per specs/locations.md.
EXTRACTORS = {
    "internal_ssd":  "diskutil_apfs",
    "external_ssd":  "diskutil_apfs",
    "external_hdd":  "diskutil_apfs",
    "device":        "lockdown",
    "cloud_object":  "declared_host",
    "other":         "diskutil_other",
}

# Strong identifiers per medium (the verification policy: any match → pass).
STRONG_IDS = {
    "internal_ssd":  ("volume_uuid", "media_serial"),
    "external_ssd":  ("volume_uuid", "media_serial"),
    "external_hdd":  ("volume_uuid", "media_serial"),
    "device":        ("unique_device_id",),
    "cloud_object":  ("host",),
    "other":         ("volume_uuid", "media_serial"),
}


# ── Extractors ────────────────────────────────────────────────────────────────

def _volume_mount_for(path):
    """Walk up from `path` to the actual volume mount point.

    `diskutil info` accepts a volume's mount point (`/`, `/Volumes/foo`), not an
    arbitrary subdirectory of it. We declare `mount_point` as the archive root
    on a medium (e.g. `/Users/maik/selfhosted`), which is a subdirectory of the
    volume's real mount — so resolve it before invoking diskutil.
    """
    p = Path(path).resolve()
    while not p.is_mount() and p != p.parent:
        p = p.parent
    return p if p.is_mount() else None


def _diskutil_plist(path):
    """`diskutil info -plist` for whichever volume `path` lives on, parsed to a dict."""
    if not Path(path).exists():
        raise RuntimeError(f"mount point not present: {path}")
    mount = _volume_mount_for(path)
    if mount is None:
        raise RuntimeError(f"could not find a volume mount above: {path}")
    proc = subprocess.run(
        ["diskutil", "info", "-plist", str(mount)],
        capture_output=True, check=True)
    return plistlib.loads(proc.stdout)


def _try_usb_serial(whole_disk):
    """Best-effort: walk ioreg text output to find the USB serial of `whole_disk`.

    Returns the serial string, or None if not found / not a USB-attached medium
    (e.g. the Apple Silicon internal SSD has no exposed USB serial).
    """
    if not whole_disk:
        return None
    try:
        out = subprocess.run(
            ["ioreg", "-l", "-w", "0", "-c", "IOUSBHostDevice"],
            capture_output=True, check=True, text=True).stdout
    except Exception:
        return None
    # Heuristic: in ioreg's tree-text, a BSD Name line and the USB Serial Number
    # line live in the same device subtree. Scan for the whole_disk's bsd_name,
    # then walk backwards for the nearest "USB Serial Number".
    lines = out.splitlines()
    bsd_pat = re.compile(r'"BSD Name"\s*=\s*"' + re.escape(whole_disk) + r'"')
    serial_pat = re.compile(r'"USB Serial Number"\s*=\s*"([^"]+)"')
    for i, line in enumerate(lines):
        if bsd_pat.search(line):
            for j in range(i, -1, -1):
                m = serial_pat.search(lines[j])
                if m:
                    return m.group(1)
            return None
    return None


def _is_multi_partition(location):
    """True when a location declares `partitions` (one physical disk holding
    more than one volume) rather than a single top-level `mount_point`."""
    return "partitions" in location


def extract_diskutil_apfs(location):
    """Identifiers for an APFS volume at `location.mount_point`, or -- for a
    multi-partition location -- one physical disk's `media_serial` (shared,
    enclosure-level) plus a per-partition `volume_uuid`/`disk_uuid`/`volume_name`
    for each entry in `location.partitions`."""
    if _is_multi_partition(location):
        partitions = {}
        media_serial = None
        for name, part in location["partitions"].items():
            info = _diskutil_plist(part["mount_point"])
            partitions[name] = {
                "volume_uuid":  info.get("VolumeUUID"),
                "disk_uuid":    info.get("DiskUUID"),
                "volume_name":  info.get("VolumeName"),
            }
            if media_serial is None:
                media_serial = _try_usb_serial(info.get("ParentWholeDisk"))
        return {"media_serial": media_serial, "partitions": partitions}
    info = _diskutil_plist(location["mount_point"])
    return {
        "volume_uuid":  info.get("VolumeUUID"),
        "disk_uuid":    info.get("DiskUUID"),
        "volume_name":  info.get("VolumeName"),
        "media_serial": _try_usb_serial(info.get("ParentWholeDisk")),
    }


def extract_other(location):
    """Identifiers for the free-form `other` medium -- e.g. an SD card in a
    card reader, which has no dedicated closed-enum medium of its own (see
    specs/locations.md). Real gap found 2026-07-24: `other` was declared in the
    medium enum from the start but had no entry in `EXTRACTORS` at all, so any
    project opting into hardware verification (`"location": <other-medium-id>`
    in config.json) would hit `extract()`'s `RuntimeError` and get treated as
    `extraction_failed` -- a hard refuse on every single command, not the soft
    "no identification yet" this medium's free-form nature should produce.

    Same diskutil + USB-ioreg probe as `extract_diskutil_apfs`, deliberately
    filesystem-agnostic rather than assuming APFS: `diskutil info -plist`
    returns `VolumeUUID`/`DiskUUID` for many non-APFS filesystems too, but for
    a bare FAT/exFAT SD card with no real identity exposed by macOS, every
    field routinely comes back null -- confirmed for real against an actual
    Samsung SD card via `community.sd_card_file_registry`'s own independent
    probe (SerialNumber and Model both "Unknown"). `identify()`/`verify()`
    already treat an all-null strong-identifier set as `no_identification` (a
    soft warning), never a hard failure, so a card with no exposed hardware
    identity is an expected, non-blocking outcome here -- not a bug to work
    around by mislabeling the medium as `external_ssd` just to get a working
    extractor.
    """
    info = _diskutil_plist(location["mount_point"])
    return {
        "volume_uuid":  info.get("VolumeUUID"),
        "disk_uuid":    info.get("DiskUUID"),
        "volume_name":  info.get("VolumeName"),
        "media_serial": _try_usb_serial(info.get("ParentWholeDisk")),
    }


def extract_lockdown(_location):
    """Identifiers for a connected iOS device via pymobiledevice3."""
    try:
        from pymobiledevice3.lockdown import create_using_usbmux
    except ImportError as e:
        raise RuntimeError(f"pymobiledevice3 not available: {e}")

    async def go():
        lockdown = await create_using_usbmux()
        info = lockdown.all_values
        return {
            "unique_device_id": info.get("UniqueDeviceID"),
            "serial_number":    info.get("SerialNumber"),
            "unique_chip_id":   info.get("UniqueChipID"),
            "product_type":     info.get("ProductType"),
        }
    return asyncio.run(go())


def extract_declared_host(location):
    """For cloud_object, the strong identifier is the declared host — no extraction.

    Read it straight from location.json's `host`, or fall back to a parsed
    identification.json (the spec says cloud's identification.json mirrors the
    declared host for shape uniformity).
    """
    return {"host": location.get("host")
            or (location.get("identification") or {}).get("identifiers", {}).get("host")}


def extract(location):
    """Dispatch to the appropriate extractor for this location's medium."""
    medium = location["medium"]
    if medium not in EXTRACTORS:
        raise RuntimeError(f"no extractor registered for medium {medium!r}")
    name = EXTRACTORS[medium]
    fn = {
        "diskutil_apfs":  extract_diskutil_apfs,
        "diskutil_other": extract_other,
        "lockdown":       extract_lockdown,
        "declared_host":  extract_declared_host,
    }[name]
    return fn(location)


# ── Identification & verification ─────────────────────────────────────────────

def _match(recorded, live, strong):
    """Compare recorded vs live identifiers for `strong` keys.

    Returns (matched, mismatches) where mismatches is [(key, recorded, live), …].
    A key with `None` on either side is *skipped* (not a match, not a mismatch).
    """
    matched, mismatches = [], []
    for s in strong:
        rec, new = recorded.get(s), live.get(s)
        if rec is None or new is None:
            continue
        if rec == new:
            matched.append(s)
        else:
            mismatches.append((s, rec, new))
    return matched, mismatches


def _match_multi(recorded, live):
    """Compare recorded vs live identifiers for a multi-partition location:
    the shared enclosure-level `media_serial`, plus each named partition's own
    `volume_uuid`. Returns (matched, mismatches) shaped like `_match`'s, with
    partition-scoped keys as `"partitions.<name>.volume_uuid"` so a mismatch
    names exactly which partition drifted. A partition present on only one
    side (recorded or live) is skipped, same as a `None` value in `_match`.
    """
    matched, mismatches = [], []
    rec_serial, live_serial = recorded.get("media_serial"), live.get("media_serial")
    if rec_serial is not None and live_serial is not None:
        if rec_serial == live_serial:
            matched.append("media_serial")
        else:
            mismatches.append(("media_serial", rec_serial, live_serial))
    rec_parts, live_parts = recorded.get("partitions", {}), live.get("partitions", {})
    for name, rec_part in rec_parts.items():
        live_part = live_parts.get(name)
        if live_part is None:
            continue
        rec_uuid, live_uuid = rec_part.get("volume_uuid"), live_part.get("volume_uuid")
        if rec_uuid is None or live_uuid is None:
            continue
        key = f"partitions.{name}.volume_uuid"
        if rec_uuid == live_uuid:
            matched.append(key)
        else:
            mismatches.append((key, rec_uuid, live_uuid))
    return matched, mismatches


def verify(location):
    """Check live identifiers against the location's recorded `identification.json`.

    Returns (status, details). Status ∈
      `match`               — at least one strong identifier matched, none mismatched
      `partial`             — at least one strong matched AND at least one mismatched
                               (interesting — see spec's open question on partial)
      `drift`               — every strong identifier we could compare mismatched
      `no_identification`   — identification.json missing
      `extraction_failed`   — could not read live (e.g. mount absent)
    """
    folder = location["location_folder"]
    ident_path = folder / "identification.json"
    if not ident_path.exists():
        return "no_identification", {}
    recorded = json.loads(ident_path.read_text())["identifiers"]
    try:
        live = extract(location)
    except Exception as e:
        return "extraction_failed", {"error": str(e)}
    if _is_multi_partition(location):
        matched, mismatches = _match_multi(recorded, live)
    else:
        matched, mismatches = _match(recorded, live, STRONG_IDS[location["medium"]])
    if not matched and not mismatches:
        # Nothing comparable — every strong id was None on at least one side.
        return "no_identification", {"note": "all strong identifiers null"}
    if not matched:
        return "drift", {"mismatches": mismatches, "live": live}
    if mismatches:
        return "partial", {"matched": matched, "mismatches": mismatches, "live": live}
    return "match", {"matched": matched}


def identify(location):
    """Establish or refresh `identification.json` from a live extraction.

    First run: write the file from scratch.
    Re-run: accept only if at least one strong identifier still matches the
    recorded one; refresh non-strong fields. On drift, leave the file untouched.
    Returns (status, details).
    """
    folder = location["location_folder"]
    ident_path = folder / "identification.json"
    extractor_name = EXTRACTORS[location["medium"]]
    live = extract(location)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    if not ident_path.exists():
        ident_path.write_text(json.dumps({
            "identifiers": live,
            "recorded_at": now,
            "extractor":   extractor_name,
        }, indent=2) + "\n")
        return "established", {"identifiers": live}

    recorded_doc = json.loads(ident_path.read_text())
    if _is_multi_partition(location):
        matched, mismatches = _match_multi(recorded_doc["identifiers"], live)
    else:
        matched, mismatches = _match(
            recorded_doc["identifiers"], live, STRONG_IDS[location["medium"]])
    if not matched:
        return "drift", {"mismatches": mismatches, "live": live}
    recorded_doc["identifiers"] = live
    recorded_doc["recorded_at"] = now
    recorded_doc["extractor"]   = extractor_name
    ident_path.write_text(json.dumps(recorded_doc, indent=2) + "\n")
    return "refreshed", {"matched": matched, "mismatches": mismatches}


# ── Pipeline integration ──────────────────────────────────────────────────────

def pipeline_location_for(project, locations):
    """Find the archive_target whose location's mount_point is a prefix of the
    project_folder — i.e. the location the pipeline currently reads/writes to.

    Returns (location, target) or (None, None).
    """
    project_folder = str(project["project_folder"])
    for tgt in project.get("archive_targets", []) or []:
        loc = locations.get(tgt["location"])
        if loc is None:
            continue
        mount_point = str(loc["mount_point"])
        if (project_folder == mount_point
                or project_folder.startswith(mount_point.rstrip("/") + "/")):
            return loc, tgt
    return None, None


def verify_pipeline_location(project, locations):
    """Silent precondition for pipeline stages: verify the active write location,
    refuse on identity drift. Per Maik's step-5 choice (b): only the location the
    pipeline currently writes to, not every declared archive_target.

    Bypass with `SKIP_IDENTITY=1` (genuine first-install only; never silent).
    """
    if os.environ.get("SKIP_IDENTITY"):
        print(f"  ! SKIP_IDENTITY set — bypassing identity verification for "
              f"{project['id']}", file=sys.stderr)
        return
    location, _target = pipeline_location_for(project, locations)
    if location is None:
        # No archive_targets declared, or none covers the project_folder. Skip
        # with a one-line notice rather than refuse — the project may not have
        # been migrated to the locations scheme yet.
        print(f"  ! {project['id']}: no archive_target covers {project['project_folder']}; "
              f"skipping identity verification", file=sys.stderr)
        return
    status, details = verify(location)
    if status == "match":
        # Silent success per spec — but record a `verified_identity` event per use,
        # so each stage run × location used leaves an honest provenance trail.
        archive_ledger.record_event(
            kind="verified_identity",
            location_id=location["id"],
            project_id=project["id"],
            agent="location_identity.py",
            notes=f"strong identifiers matched: {','.join(details['matched'])}",
        )
        return
    if status == "partial":
        print(f"  ! identity partial match for {location['id']}: "
              f"matched={details['matched']}, "
              f"mismatched={[m[0] for m in details['mismatches']]}",
              file=sys.stderr)
        return
    if status == "no_identification":
        print(f"  ! {location['id']}: no identification.json — run "
              f"`weasel run verify_identity` first", file=sys.stderr)
        return
    # drift / extraction_failed → loud refuse, exit non-zero
    print(f"\nidentity drift: refusing to use {location['id']} "
          f"(mount_point: {location['mount_point']})", file=sys.stderr)
    if status == "drift":
        for s, rec, new in details.get("mismatches", []):
            print(f"  {s}:\n    expected: {rec}\n    found:    {new}",
                  file=sys.stderr)
    else:
        print(f"  extraction error: {details.get('error', '')}", file=sys.stderr)
    sys.exit(2)


# ── CLI: `weasel run verify_identity` ─────────────────────────────────────────

STATUS_GLYPH = {
    "match": "✓", "partial": "~", "drift": "✗",
    "no_identification": "?", "extraction_failed": "!",
    "established": "+", "refreshed": "✓",
}


def main():
    """Sweep every registered location: verify an already-identified one,
    establish identity for one that's brand new.

    Real gap found 2026-07-24: this only ever called `verify()`, which reads
    an existing `identification.json` and never creates one -- so a freshly
    registered location (a `location.json` with no sibling `identification.json`
    yet) had no CLI path to actually get identified at all; the only way to
    populate that file was an ad-hoc one-off script. Now: if a location has no
    `identification.json`, call `identify()` instead (first-time
    establishment, live probe against the medium's extractor), and report
    "established" rather than silently leaving it unidentified.
    """
    locations = select_locations()
    if not locations:
        print("no locations registered — declare some under ~/selfhosted/locations/")
        return
    headers = ("location", "status", "detail")
    widths  = (24, 18, 0)
    print(f"{headers[0]:<{widths[0]}}  {headers[1]:<{widths[1]}}  {headers[2]}")
    print("─" * 70)
    for lid, loc in locations.items():
        ident_path = loc["location_folder"] / "identification.json"
        if not ident_path.exists():
            try:
                status, details = identify(loc)
            except Exception as e:
                status, details = "extraction_failed", {"error": str(e)}
        else:
            status, details = verify(loc)
        glyph = STATUS_GLYPH.get(status, " ")
        if status == "established":
            detail = f"identity established: {details['identifiers']}"
        elif status == "match":
            detail = f"matched={','.join(details['matched'])}"
        elif status == "partial":
            detail = (f"matched={','.join(details['matched'])} "
                      f"mismatched={[m[0] for m in details['mismatches']]}")
        elif status == "no_identification":
            detail = details.get("note", "no identification.json")
        elif status == "drift":
            detail = ("all strong identifiers mismatched — "
                      + ", ".join(m[0] for m in details["mismatches"]))
        elif status == "extraction_failed":
            detail = (details.get("error", "") or "")[:60]
        else:
            detail = ""
        print(f"{lid:<{widths[0]}}  {glyph} {status:<{widths[1]-2}}  {detail}")


if __name__ == "__main__":
    main()
