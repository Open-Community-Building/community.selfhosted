#!/usr/bin/env python3
"""
Convert a Google Takeout mail export (mbox) into an SQLite database suitable for
exploration in Datasette, by delegating to the companion `memex` package
(`memex gmail`). The mbox is located via each mail project's configured storage.
"""

import glob
import os
import subprocess
import sys

from project_registry import load_projects

projects = load_projects()


def find_mbox(folder):
    """Return the Takeout mbox inside `folder`, or None if there isn't one.

    Google Takeout names it "All mail Including Spam and Trash.mbox"; fall back
    to any single *.mbox in the folder.
    """
    candidates = sorted(glob.glob(os.path.join(folder, "*.mbox")))
    for c in candidates:
        if os.path.basename(c) == "All mail Including Spam and Trash.mbox":
            return c
    return candidates[0] if candidates else None


def run(project):
    output_file = project['project_folder'] / 'gmail_sqlite' / 'gmail.sqlite'
    if os.path.exists(output_file):
        print("Sampling instead of running the whole process")
        output_file = output_file.with_stem(output_file.stem + "_sample")

    folder = project["primary_storage"] or project["secondary_storage"]
    if not folder:
        print(f"No storage configured for {project['id']}; skipping")
        return

    mbox = find_mbox(folder)
    if mbox is None:
        print(f"No .mbox found under {folder}; skipping {project['id']}")
        return

    output_file.parent.mkdir(parents=True, exist_ok=True)

    # Convert via the companion community.memex package: memex gmail MBOX DB.
    subprocess.run(
        [sys.executable, "-m", "memex", "gmail", str(mbox), str(output_file)],
        check=True,
    )


def main():
    for projectid in projects.keys():
        project = projects[projectid]
        if project["source"] not in ["Google Takeout Mail"]:
            continue
        run(project)


if __name__ == "__main__":
    main()
