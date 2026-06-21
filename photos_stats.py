import json
import os

from config import photo_projects as projects

def human_readable_size(size_bytes):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024 or unit == 'TB':
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024

def stats(project):
    if os.path.exists(project['processed_stats']):
        print("Ignoring project %s, because result file already exists: %s" % (project['id'], project['processed_stats']))
        return
    md5 = json.loads(open(project['processed_md5'], 'r').read())
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
    json.dump(result, open(project['processed_stats'], 'w'), indent=4, ensure_ascii=False, sort_keys=True)

def main():
    for projectid in projects.keys():
        project = projects[projectid]
        stats(project)

if __name__ == "__main__":
    main()
