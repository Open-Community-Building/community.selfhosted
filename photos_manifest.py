"""Build the Source Manifest for each photo project — see specs/source-manifest.md.

The photos *item iterator*: one item per file under a project's storage folder,
yielding the file path as the locator and the file itself as content. The generic
`manifest.build` fingerprints each file and writes a standalone SQLite index at
`photos_manifest/manifest.sqlite` in the project folder.
"""

import os
from datetime import datetime, timezone

import manifest
from project_registry import load_projects

projects = load_projects()

PHOTO_SOURCES = ["Google Takeout", "AndroidPhotoBackup", "IPad", "IPhone"]


def iter_photo_items(folder):
    """Yield (kind, locator, locator_kind, content, features) per file under `folder`.

    content is the file path — manifest.build streams it to compute the MD5.
    """
    for directory, _, files in os.walk(folder):
        for name in files:
            if name.endswith(".DS_Store"):
                continue
            path = os.path.join(directory, name)
            ext = os.path.splitext(name)[1].lower()
            try:
                mtime = datetime.fromtimestamp(
                    os.path.getmtime(path), tz=timezone.utc).isoformat()
            except OSError:
                mtime = None
            yield "file", path, "path", path, {"ext": ext, "mtime": mtime}


def process(project):
    folder = project["primary_storage"] or project["secondary_storage"]
    db_path = project["project_folder"] / "photos_manifest" / "manifest.sqlite"
    n = manifest.build(db_path, iter_photo_items(folder))
    print(f"{project['id']}: {n} items -> {db_path}")


def main():
    for projectid in projects.keys():
        project = projects[projectid]
        if project["source"] not in PHOTO_SOURCES:
            continue
        # Opt-in per project, mirroring photos_md5: only build where the
        # photos_manifest/ directory has been created.
        if (project["project_folder"] / "photos_manifest").is_dir():
            process(project)


if __name__ == "__main__":
    main()
