import hashlib
import json
import os

from config import photo_projects as projects

def dump(project):
    if os.path.exists(project['processed_md5']):
        print("Ignoring project %s, because result file already exists: %s" % (project['id'], project['processed_md5']))
        return
    result = {}
    for directory, _, files in os.walk(project['fetched_folder']):
        for name in files:
            if name.endswith(".DS_Store"):
                continue
            path = os.path.join(directory, name)
            info = {}
            info["path"] = path
            info['name'] = name
            info['md5sum'] = md5(path)
            info['size'] = os.path.getsize(path)
            result[path] = info
    json.dump(result, open(project['processed_md5'], 'w'), indent=4, ensure_ascii=False, sort_keys=True)

def main():
    for projectid in projects.keys():
        project = projects[projectid]
        dump(project)

if __name__ == "__main__":
    main()
