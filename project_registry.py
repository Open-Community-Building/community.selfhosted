"""Project configuration, resolved via spaCy's config system.

Implements specs/configure_projects.md: configuration is declared in config.cfg and
resolved with spacy.registry, replacing the hand-written config.py. Discovery is a
registered function (the Photo Discovery behavior in specs/photo-registry.md) and is
side-effect free — creating each project's working directories is the explicit
ensure_dirs() step, not a side effect of resolution.
"""
import argparse
import json
import os
import sys
from pathlib import Path
from pprint import pprint

import spacy
from confection import Config

DEFAULT_CONFIG = Path(__file__).with_name("config.cfg")


@spacy.registry.misc("photo_projects.discover.v1")
def discover_projects(root: str) -> dict:
    """Discover photo projects under `root` and build the project registry.

    Reads each project's config.json and computes its paths. Pure: creates no
    directories (see ensure_dirs).
    """
    root = Path(root).expanduser()
    projects: dict = {}
    for folder in sorted(f for f in root.iterdir()
                         if f.is_dir() and not f.name.startswith(".")):
        project = json.loads((folder / "config.json").read_text())
        project["id"] = folder.name
        project["project_folder"] = folder
        project["dump_folder"] = folder / "dump"
        project["dump_pymobiledevice3_files"] = folder / "dump" / "pymobiledevice3_files.json"
        project["identification_folder"] = folder / "identification"
        project["identification_info"] = folder / "identification" / "info.json"
        project["fetched_folder"] = folder / "fetched"
        project["processed_folder"] = folder / "processed"
        project["processed_md5"] = folder / "processed" / "md5.json"
        project["processed_stats"] = folder / "processed" / "stats.json"
        project["processed_metadata"] = folder / "processed" / "metadata.json"
        projects[folder.name] = project
    return projects


def load_projects(config_path=DEFAULT_CONFIG) -> dict:
    """Resolve config.cfg through spacy.registry and return the project registry."""
    config = Config().from_disk(config_path)
    return spacy.registry.resolve(config)["projects"]


def ensure_dirs(projects: dict) -> None:
    """Explicit side-effect step: create each project's fetched/ and processed/ dirs."""
    for project in projects.values():
        project["fetched_folder"].mkdir(parents=True, exist_ok=True)
        project["processed_folder"].mkdir(parents=True, exist_ok=True)


def select_projects(argv=None, projects=None) -> dict:
    """Load the registry filtered to one project, when `--project <id>` (or `PROJECT`
    env var) selects one. The env var is the path weasel takes — `weasel run <cmd>`
    can't forward CLI args, so `PROJECT=<id> weasel run <cmd>` is the way.

    No selection → all projects, unchanged. Unknown id → exit listing valid ones.
    """
    if projects is None:
        projects = load_projects()
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("-p", "--project", default=os.environ.get("PROJECT"))
    args, _ = parser.parse_known_args(argv)
    if not args.project:
        return projects
    if args.project not in projects:
        valid = "\n  ".join(sorted(projects))
        sys.exit(f"unknown project {args.project!r}\nconfigured projects:\n  {valid}")
    print(f"  → restricted to project: {args.project}", file=sys.stderr)
    return {args.project: projects[args.project]}


if __name__ == "__main__":
    pprint(select_projects())
