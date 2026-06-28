#!/usr/bin/env python3
"""
Per-project 3-2-1-1-0 compliance check — see specs/locations.md.

For each project, evaluate the backup strategy over its archive_targets:
  **3** copies, on **2** distinct media, with **1** off-site, **1** offline,
  **0** errors after fixity verification.

Compliance is **per project** (locations come and go; projects remain) and is
evaluated over **materialised** archive_targets — those whose resolved path
actually exists today. Three resolution modes:

- **Disk, online** — local `Path.exists()` against `mount_point + target.path`.
- **Disk, declared `online_state: "offline"`** (the USB-in-a-drawer pattern) —
  `Path.exists()` first; if absent (drive unplugged, expected), accept a
  `verified` event within the freshness window as proof the data was there the
  last time we plugged in. The drawer drive's *whole point* is to not be online
  most of the time — checking `Path.exists()` while it's in the drawer would
  always fail, defeating the purpose.
- **Cloud** — SFTP probe via `location.ssh_alias`. Without an alias, the cloud
  target is treated as not materialised.

Read-only on data; the SFTP probe is a single short network round-trip per cloud
target (~0.5 s). The **`verified`** leg reads `verified` events from
`~/selfhosted/archive/archive.sqlite/events` against a 90-day freshness window.
"""

import subprocess
from pathlib import Path

import archive_ledger
from project_registry import load_locations, select_projects

# A location satisfies the "1 offline" leg when its online_state is offline or
# immutable (air-gapped or WORM); either is acceptable.
OFFLINE_STATES = {"offline", "immutable"}

# Verification freshness window per specs/locations.md (Constraints): 90 days,
# global, simpler than per-location overrides and field-typical for preservation.
FRESHNESS_DAYS = 90

# Cloud probe timeout — single SFTP `cd` round-trip; ample for any sane network.
PROBE_TIMEOUT = 15


def _probe_disk_path(location, path):
    """For disk-medium locations: is `mount_point/path` materialised?

    Online disks (default): a straight `Path.exists()`.
    Offline disks (`online_state: "offline"`, the drawer-drive pattern): if the
    path is absent (drive unplugged), trust a recent `verified` event from the
    archive ledger — it proves we plugged it in within the freshness window and
    the content checksumed cleanly. Returns (exists, note); note is set only
    when the result reflects a non-obvious decision.
    """
    full = Path(location["mount_point"]) / path
    if full.exists():
        return True, None
    if location.get("online_state") == "offline":
        ev = archive_ledger.latest_event("verified", location_id=location["id"])
        if archive_ledger.within(ev, FRESHNESS_DAYS):
            return True, (f"offline (drawer) — trusting verified event "
                          f"from {ev['when_'][:10]}")
        return False, ("offline (drawer) — no `verified` event within "
                       f"{FRESHNESS_DAYS}d; plug in to refresh")
    return False, None


def _probe_cloud_path(location, path):
    """SFTP probe: does `<path>` exist on the location's cloud server?

    Returns (exists, note). `exists` is True iff the SFTP `cd <path>` succeeds.
    Any failure path — no ssh_alias, network/auth error, timeout — returns False
    with a `note` describing why (so the per-target output is honest about
    *whether we could check*, not just the result).
    """
    alias = location.get("ssh_alias")
    if not alias:
        return False, "no ssh_alias in location.json — can't probe"
    try:
        proc = subprocess.run(
            ["sftp", "-q", "-b", "-", "-o", "BatchMode=yes", alias],
            input=f"cd {path}\n",
            capture_output=True, text=True, timeout=PROBE_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return False, f"sftp probe timed out (> {PROBE_TIMEOUT}s)"
    except OSError as exc:
        return False, f"sftp probe failed: {exc}"
    if proc.returncode == 0:
        return True, None
    return False, (proc.stderr.strip().splitlines()[-1]
                   if proc.stderr.strip() else "path not found")


def evaluate(project, locations):
    """Compute compliance for one project. Returns a dict of legs + status."""
    home_site = project.get("home_site", "home")
    targets = project.get("archive_targets", []) or []

    # Resolve each declared archive_target and check whether its path is materialised.
    # Disks: local Path.exists() against mount_point + path.
    # Cloud: SFTP probe via location.ssh_alias (single short round-trip per target).
    resolved = []
    for tgt in targets:
        loc_id = tgt["location"]
        loc = locations.get(loc_id)
        if loc is None:
            resolved.append({"target": tgt, "exists": False,
                             "note": f"unknown_location:{loc_id}"})
            continue
        if loc["medium"] == "cloud_object":
            exists, note = _probe_cloud_path(loc, tgt["path"])
            display = f"{loc.get('ssh_alias', '?')}:{tgt['path']}"
        else:
            exists, note = _probe_disk_path(loc, tgt["path"])
            display = Path(loc["mount_point"]) / tgt["path"]
        entry = {"target": tgt, "location": loc, "full_path": display,
                 "exists": exists}
        if note:
            entry["note"] = note
        resolved.append(entry)

    materialised = [r for r in resolved if r.get("exists")]
    copies = len(materialised)
    media_set = {r["location"]["medium"] for r in materialised}
    media = len(media_set)
    offsite = any(r["location"]["site"] != home_site for r in materialised)
    offline = any(r["location"]["online_state"] in OFFLINE_STATES for r in materialised)
    # Per-location `verified` events from the archive ledger (content fixity passed,
    # within FRESHNESS_DAYS). The leg is the AND across materialised locations.
    verified_by_loc = {}
    for r in materialised:
        ev = archive_ledger.latest_event("verified", location_id=r["location"]["id"])
        verified_by_loc[r["location"]["id"]] = archive_ledger.within(ev, FRESHNESS_DAYS)
    all_verified = bool(materialised) and all(verified_by_loc.values())

    failing = []
    if copies < 3:
        failing.append(f"copies({copies}<3)")
    if media < 2:
        failing.append(f"media({media}<2)")
    if not offsite:
        failing.append("offsite")
    if not offline:
        failing.append("offline")
    if materialised and not all_verified:
        stale = [lid for lid, ok in verified_by_loc.items() if not ok]
        failing.append(f"verified({','.join(stale)})")

    if copies == 0:
        status = "not_yet_evaluable"
    elif failing:
        status = "non_compliant"
    else:
        status = "compliant"

    return {
        "status": status, "copies": copies, "media": media, "media_set": media_set,
        "offsite": offsite, "offline": offline, "all_verified": all_verified,
        "verified_by_loc": verified_by_loc,
        "failing": failing, "resolved": resolved,
    }


def render(rows):
    """Pretty-print a compliance summary table."""
    headers = ("project", "status", "copies", "media", "off-site", "off-line", "verified")
    widths = (32, 19, 6, 5, 8, 8, 8)
    print("  ".join(h.ljust(w) for h, w in zip(headers, widths)))
    print("─" * (sum(widths) + 2 * (len(widths) - 1)))
    counts = {}
    for pid, row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
        if not row["resolved"]:
            verified = "—"
        else:
            verified = "✓" if row["all_verified"] else "✗"
        line = "  ".join(s.ljust(w) for s, w in zip([
            pid, row["status"], str(row["copies"]), str(row["media"]),
            "✓" if row["offsite"] else "✗",
            "✓" if row["offline"] else "✗", verified,
        ], widths))
        print(line)
        # Per-target detail: show what's materialised and what isn't, when
        # there's anything actionable (failures or unknown locations).
        if row["failing"] or any("note" in r for r in row["resolved"]):
            for r in row["resolved"]:
                if r.get("location") is None:
                    # Unknown location id (typo in archive_targets) — the note is the whole story
                    print(f"    ! {r.get('note', '?')}")
                else:
                    tick = "✓" if r["exists"] else "✗"
                    print(f"    {tick} {r['target']['location']}: {r['full_path']}")
                    if "note" in r:
                        print(f"        ({r['note']})")
            if row["failing"]:
                print(f"    ↳ failing: {', '.join(row['failing'])}")
    print()
    total = len(rows)
    summary_order = ("compliant", "non_compliant", "not_yet_evaluable")
    summary = "  ".join(f"{counts.get(k, 0)} {k}" for k in summary_order)
    print(f"{total} project(s): {summary}")


def main():
    projects = select_projects()
    locations = load_locations()
    rows = [(pid, evaluate(p, locations)) for pid, p in projects.items()]
    render(rows)


if __name__ == "__main__":
    main()
