#!/usr/bin/env python3
"""
Per-project 3-2-1-1-0 compliance check — see specs/locations.md.

For each project, evaluate the backup strategy over its archive_targets:
  **3** copies, on **2** distinct media, with **1** off-site, **1** offline,
  **0** errors after fixity verification.

Compliance is **per project** (locations come and go; projects remain) and is
evaluated over **materialised** archive_targets — those whose resolved path
(`location.mount_point + target.path`) actually exists on disk today.

Read-only: no data files written. The **`verified`** leg requires the events
ledger (`~/selfhosted/archive/archive.sqlite`), wired in a later step; until
then it is reported as `n/a` and contributes a failing leg honestly.
"""

from pathlib import Path

import archive_ledger
from project_registry import load_locations, select_projects

# A location satisfies the "1 offline" leg when its online_state is offline or
# immutable (air-gapped or WORM); either is acceptable.
OFFLINE_STATES = {"offline", "immutable"}

# Verification freshness window per specs/locations.md (Constraints): 90 days,
# global, simpler than per-location overrides and field-typical for preservation.
FRESHNESS_DAYS = 90


def evaluate(project, locations):
    """Compute compliance for one project. Returns a dict of legs + status."""
    home_site = project.get("home_site", "home")
    targets = project.get("archive_targets", []) or []

    # Resolve each declared archive_target and check whether its path exists on disk.
    resolved = []
    for tgt in targets:
        loc_id = tgt["location"]
        loc = locations.get(loc_id)
        if loc is None:
            resolved.append({"target": tgt, "exists": False,
                             "note": f"unknown_location:{loc_id}"})
            continue
        full = Path(loc["mount_point"]) / tgt["path"]
        resolved.append({"target": tgt, "location": loc,
                         "full_path": full, "exists": full.exists()})

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
                if "note" in r:
                    print(f"    ! {r['note']}")
                else:
                    tick = "✓" if r["exists"] else "✗"
                    print(f"    {tick} {r['target']['location']}: {r['full_path']}")
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
