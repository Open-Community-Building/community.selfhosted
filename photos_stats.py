import hashlib
import json
import os

from config import photo_projects as projects

def md5(path):
    with open(path, "rb") as f:
        return hashlib.file_digest(f, "md5").hexdigest()

def stats(project):
    if os.path.exists(project['processed_stats']):
        return
    md5 = json.loads(open(project['processed_md5'], 'r').read())
    result = {}
    result['total'] = len(md5)
    json.dump(result, open(project['processed_stats'], 'w'), indent=4, ensure_ascii=False, sort_keys=True)

def main():
    for projectid in projects.keys():
        project = projects[projectid]
        stats(project)

if __name__ == "__main__":
    main()
