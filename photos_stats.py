import json
import os

from project_registry import load_projects

projects = load_projects()

def human_readable_size(size_bytes):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024 or unit == 'TB':
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024

def stats(project, md5):
    output_file = project['project_folder'] / 'photos_stats' / 'stats.json'
    if os.path.exists(output_file):
        print("Sampling instead of running the whole process")
        output_file = project['project_folder'] / 'photos_stats' / 'stats.sample.json'
    result = {}
    result['total'] = len(md5)
    total_size = sum(entry['size'] for entry in md5.values())
    result['total_size'] = total_size
    result['total_size_human'] = human_readable_size(total_size)
    types = {}
    for entry in md5.values():
        ext = os.path.splitext(entry['name'])[1].lower()
        types[ext] = types.get(ext, 0) + 1
    result['types'] = dict(sorted(types.items()))
    json.dump(result, open(output_file, 'w'), indent=4, ensure_ascii=False, sort_keys=True)

def main():
    for projectid in projects.keys():
        project = projects[projectid]
        if project["source"] not in ["Google Takeout", "AndroidPhotoBackup", "IPad", "IPhone"]:
            continue
        md5_path = project['project_folder'] / 'photos_md5' / 'md5.json'
        if os.path.exists(md5_path):
            md5 = json.loads(open(md5_path, 'r').read())
        else:
            continue
        stats(project, md5)

if __name__ == "__main__":
    main()
