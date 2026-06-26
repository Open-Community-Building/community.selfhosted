import json
import sqlite3

from project_registry import load_projects

projects = load_projects()

PHOTO_SOURCES = ["Google Takeout", "AndroidPhotoBackup", "IPad", "IPhone"]


def human_readable_size(size_bytes):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024 or unit == 'TB':
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024


def stats(project, db_path):
    """Compute project statistics from the Source Manifest (see specs/stats.md)."""
    output_file = project['project_folder'] / 'photos_stats' / 'stats.json'
    db = sqlite3.connect(db_path)
    # Scope to the latest ingest — the manifest is append-only (see specs/fixity.md).
    latest = "ingest_id = (SELECT MAX(id) FROM ingests)"
    total, total_size = db.execute(
        f"SELECT COUNT(*), COALESCE(SUM(size), 0) FROM items WHERE {latest}").fetchone()
    types = dict(db.execute(
        "SELECT COALESCE(json_extract(features, '$.ext'), '') AS ext, COUNT(*) "
        f"FROM items WHERE {latest} GROUP BY ext"))
    db.close()

    result = {
        'total': total,
        'total_size': total_size,
        'total_size_human': human_readable_size(total_size),
        'types': dict(sorted(types.items())),
    }
    output_file.parent.mkdir(parents=True, exist_ok=True)
    json.dump(result, open(output_file, 'w'), indent=4, ensure_ascii=False, sort_keys=True)
    print(f"{project['id']}: {total} items, {result['total_size_human']} -> {output_file}")


def main():
    for projectid in projects.keys():
        project = projects[projectid]
        if project["source"] not in PHOTO_SOURCES:
            continue
        db_path = project['project_folder'] / 'photos_manifest' / 'manifest.sqlite'
        if db_path.exists():
            stats(project, db_path)


if __name__ == "__main__":
    main()
