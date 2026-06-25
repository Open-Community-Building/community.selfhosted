import hashlib
import json
import os
import random

from project_registry import load_projects

projects = load_projects()

def md5(path):
    with open(path, "rb") as f:
        return hashlib.file_digest(f, "md5").hexdigest()

def process(project, sample):
    output_file = project['project_folder'] / 'photos_md5' / 'md5.json'
    if os.path.exists(output_file):
        print("Sampling instead of running the whole process")
        output_file = output_file.with_stem(output_file.stem + "_sample")

    folder = project["primary_storage"] or project["secondary_storage"]

    result = {}
    file_infos = []
    for directory, _, files in os.walk(folder):
        for name in files:
            if name.endswith(".DS_Store"):
                continue
            path = os.path.join(directory, name)
            info = {}
            info["path"] = path
            info['name'] = name
            file_infos.append(info)
    if sample:
        file_infos = random.sample(file_infos, min(len(file_infos), 10))
    for info in file_infos:
        print(info)
        info['md5sum'] = md5(info['path'])
    for info in file_infos:
        print(info)
        info['size'] = os.path.getsize(info['path'])
    for info in file_infos:
        print(info)
        result[info['path']] = info
    json.dump(result, open(output_file, 'w'), indent=4, ensure_ascii=False, sort_keys=True)

def main():
    for projectid in projects.keys():
        project = projects[projectid]
        if projects[projectid]["source"] not in ["Google Takeout", "AndroidPhotoBackup", "IPad", "IPhone"]:
            continue
        sample = False
        if (project['project_folder'] / 'photos_md5' / 'md5.json').is_file():
            sample = True
        if (project['project_folder'] / 'photos_md5').is_dir():
            process(project, sample)

if __name__ == "__main__":
    main()


