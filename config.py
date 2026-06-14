import os
import json
from pprint import pprint
from pathlib import Path

target_folder = Path.home() / "selfhosted"
photo_target_folder = target_folder / "photos" / "projects"

photo_projects = {}

for folder in [f for f in photo_target_folder.iterdir() if not f.name.startswith(".")]:
    photo_projects[folder.name] = json.loads(open(folder / "config.json", "r").read())
    photo_projects[folder.name]['id'] = folder.name
    photo_projects[folder.name]['project_folder'] = folder
    photo_projects[folder.name]['processed_folder'] = folder / 'processed'
    if not os.path.exists(photo_projects[folder.name]['processed_folder']):
        os.mkdir(photo_projects[folder.name]['processed_folder'])
    md5_file = photo_projects[folder.name]['processed_folder'] / 'md5.json'
    photo_projects[folder.name]['processed_md5'] = md5_file
    stats_file = photo_projects[folder.name]['processed_folder'] / 'stats.json'
    photo_projects[folder.name]['processed_stats'] = stats_file

if __name__ == "__main__":
    pprint(photo_projects)
