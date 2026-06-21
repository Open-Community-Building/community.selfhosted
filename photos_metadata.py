import hashlib
import json
import os

from config import photo_projects as projects

import re
from datetime import datetime, timezone
from pathlib import Path


def takeout_timestamp(file_path: str) -> dict:
    """Build a Takeout-style creationTime dict from a YYYY/MM/DD path.

    Date comes from the path; time-of-day comes from the file's mtime
    (falls back to 00:00:00 UTC if the file name is unreadable).
    """
    p = Path(file_path)
    m = re.search(r"/(\d{4})/(\d{2})/(\d{2})/", file_path)
    if not m:
        raise ValueError(f"No YYYY/MM/DD found in path: {file_path}")

    year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))

    try:
        mtime = p.stat().st_mtime
        mtime_dt = datetime.fromtimestamp(mtime, tz=timezone.utc)
        hour, minute, second = mtime_dt.hour, mtime_dt.minute, mtime_dt.second
    except OSError:
        hour = minute = second = 0

    dt = datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)

    # Portable zero-stripped formatting (%-I not available on all platforms)
    time_str = dt.strftime("%I:%M:%S %p").lstrip("0")
    formatted = f"{dt.strftime('%b')} {dt.day}, {dt.year}, {time_str} UTC"

    return {
        "timestamp": str(int(dt.timestamp())),
        "formatted": formatted,
    }

def process(project):
    if os.path.exists(project['processed_metadata']):
        print("Ignoring project %s, because result file already exists: %s" % (project['id'], project['processed_metadata']))
        return
    result = {}
    md5 = json.loads(open(project['processed_md5'], 'r').read())
    metadata_by_path = {}
    for entry in list(md5.values()):
        if entry['name'].endswith('.supplemental-metadata.json'):
            with open(entry['path'], 'r') as f:
                metadata_by_path[entry['path'].split('.supplemental-metadata.json')[0]] = json.loads(f.read())

    if metadata_by_path:
        for entry in list(md5.values()):
            if entry['name'].endswith('.supplemental-metadata.json'):
                continue
            if entry['path'] in metadata_by_path:
                entry['metadata'] = metadata_by_path[entry['path']]
            else:
                entry['metadata'] = {
                    "title": entry['name'],
                    "description": "",
                    "imageViews": "0",
                    "creationTime": {
                        "timestamp": "1436182580",
                        "formatted": "Jul 6, 2015, 11:36:20 AM UTC"
                    },
                    "photoTakenTime": {
                        "timestamp": "1218472054",
                        "formatted": "Aug 11, 2008, 4:27:34 PM UTC"
                    },
                    "geoData": {
                        "latitude": 0.0,
                        "longitude": 0.0,
                        "altitude": 0.0,
                        "latitudeSpan": 0.0,
                        "longitudeSpan": 0.0
                    },
                    "url": "https://photos.google.com/photo/AF1QipPU9VkbT7JZtAHkQR18ThZ_xz24Yyga5ZtIrS8e",
                    "googlePhotosOrigin": {
                        "driveSync": {
                        }
                    }
                }
            result[entry['path']] = entry

    json.dump(result, open(project['processed_metadata'], 'w'), indent=4, ensure_ascii=False, sort_keys=True)

def main():
    for projectid in projects.keys():
        project = projects[projectid]
        process(project)

if __name__ == "__main__":
    main()


