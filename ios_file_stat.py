#!/usr/bin/env python3
"""
Fetch file stats from an iOS device suitable for exploration in Datasette.

Usage:
    python3 ios_file_stat.py
"""

import json
import os
import asyncio
from datetime import date
from datetime import datetime
from datetime import timezone
from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.services.afc import AfcService
from project_registry import load_projects

projects = load_projects()

APPLE_EPOCH = 978307200  # 1970-01-01 -> 2001-01-01, for Core Data dates

image_exts = (".heic", ".jpg", ".jpeg", ".png", ".dng", ".gif")
movie_exts = (".mov", ".mp4", ".m4v")


def json_default(o):
    if isinstance(o, (datetime, date)):
        return o.isoformat()
    raise TypeError(f"Object of type {o.__class__.__name__} is not JSON serializable")


def as_datetime(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    # fallback for builds that return ns-since-epoch as str/int
    seconds = int(value) / 1_000_000_000
    return datetime.fromtimestamp(seconds, tz=timezone.utc)

async def dump(project):
    lockdown = await create_using_usbmux()

    for projectid in projects.keys():
        project = projects[projectid]
        if project["source"] not in ["IPhone", "IPad"]:
            continue
        info = lockdown.all_values
        if info["UniqueDeviceID"] != project["source_UniqueDeviceID"]:
            continue
        else:
            if os.path.exists(project['dump_pymobiledevice3_files']):
                print("Ignoring project %s, because result file already exists: %s" % (project['id'],
                                                                                   project[
                                                                                       'dump_pymobiledevice3_files']))
                return
            break

    async with AfcService(lockdown) as afc:
        result = {}
        async for root, dirs, files in afc.walk("/"):
            for name in files:
                path = root.rstrip("/") + "/" + name
                st = await afc.stat(path)
                lower = name.lower()
                kind = "other"
                if lower.endswith(image_exts):
                    kind = "image"
                elif lower.endswith(movie_exts):
                    kind = "movie"
                rec = {}
                rec["path"] = path
                rec["kind"] = kind
                rec["size"] = int(st.get("st_size", 0))
                rec["ifmt"] = st.get("st_ifmt")
                rec["mtime"] = as_datetime(st.get("st_mtime"))
                rec["birthtime"] = as_datetime(st.get("st_birthtime"))
                result[path] = rec
        json.dump(result, open(project['dump_pymobiledevice3_files'], 'w'), indent=4, ensure_ascii=False, sort_keys=True, default=json_default)

def main():
    asyncio.run(dump(projects))

if __name__ == "__main__":
    main()
