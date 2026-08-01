"""Mirror LostInTranslation's own Storage Box data -- every declared shard's
translations/recordings, plus the AI Coach's permanent call log -- down into
this project's fetched/ folder.

Delegates the actual transfer to the community.storagebox_dump package
(pip install -e ../community.storagebox_dump) -- this script only knows WHICH
bases to pull and WHERE they land locally; storagebox_dump knows HOW. Two
transports are supported, selected per project by config.json's
storage_box_auth ("ssh_key", the default, or "password") -- see
specs/lostintranslation_storagebox_dump.md.
"""
import sys

from project_registry import select_projects
from storagebox_dump import dump_bases, dump_bases_sftp

DEFAULT_SSH_ALIAS = "storage-box-subaccount-selfhosted"
DEFAULT_PORT = 23


def main() -> int:
    projects = select_projects()
    exit_code = 0
    ran_any = False
    for project in projects.values():
        if project.get("source") != "LostInTranslation":
            continue
        ran_any = True
        bases = project.get("storage_box_bases") or []
        if not bases:
            print(f"  ! {project['id']}: no storage_box_bases declared in config.json, skipping",
                  file=sys.stderr)
            continue
        # Each declared base is a shard/agent id (e.g. "1-mkrdr", "a-coach") -- the
        # app's own remote layout is "<base>/LostInTranslation/..." (see
        # specs/lostintranslation_storagebox_dump.md Definitions) -- add the fixed
        # suffix here so config.json only has to name the bases once.
        remote_bases = [f"{base}/LostInTranslation" for base in bases]
        auth = project.get("storage_box_auth", "ssh_key")
        if auth == "password":
            host = project.get("storage_box_host")
            username = project.get("storage_box_username")
            if not host or not username:
                print(f"  ! {project['id']}: storage_box_auth is \"password\" but "
                      f"storage_box_host/storage_box_username are missing, skipping",
                      file=sys.stderr)
                exit_code = 1
                continue
            port = project.get("storage_box_port", DEFAULT_PORT)
            # Password itself is never read from config.json -- resolved via the
            # macOS Keychain inside dump_bases_sftp (run `python -m storagebox_dump
            # --host ... --username ... --set-password` once beforehand).
            results = dump_bases_sftp(host, username, remote_bases, project["fetched_folder"],
                                       port=port)
        else:
            ssh_alias = project.get("storage_box_ssh_alias", DEFAULT_SSH_ALIAS)
            results = dump_bases(ssh_alias, remote_bases, project["fetched_folder"])
        for result in results:
            status = "OK" if result.ok else "FAILED"
            print(f"  [{status}] {project['id']}: {result.remote} -> {result.local}",
                  file=sys.stderr)
            if not result.ok:
                exit_code = 1
                print(f"    {result.stderr.strip()}", file=sys.stderr)
    if not ran_any:
        print("  (no LostInTranslation-sourced projects selected)", file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
