#!/usr/bin/env python3
"""
Convert the commit history of one or more local git repositories into SQLite for
exploration in Datasette — append-only, with fixity.

Each run is an *ingest*. Commits are content-addressed (the sha *is* the fixity
value), so each commit is stored once in `commits` and never overwritten; a
`commit_presence` row records that an ingest observed it. Comparing the two latest
ingests (`fixity_check`) reveals **added** commits (normal growth) and **dropped**
commits — a sha that was in history before and is gone now, i.e. a force-push /
rebase **history rewrite**. Dropped commits stay in `commits`, so rewritten-away
history is preserved.

Repositories come from a `Git Logs` project's config: `repos` is a list of
`{remote, working tree}` objects. The working tree is the local clone read with
`git log`; the remote (e.g. a GitHub URL) builds per-commit links. One project
covers many repos.
"""

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import sqlite_utils
from project_registry import load_projects

projects = load_projects()

GIT_SOURCES = ["Git Logs"]

# Record sep \x1e between commits, unit sep \x1f between fields; trailing \x1f after
# the body cleanly divides it from the --numstat block.
FMT = "\x1e%H\x1f%an\x1f%ae\x1f%aI\x1f%cn\x1f%ce\x1f%cI\x1f%P\x1f%s\x1f%b\x1f"


def repo_specs(project):
    """Parse a `Git Logs` project's `repos` into [{repo, working_tree, remote}].

    Each entry is a `{remote, working tree}` object: the working tree is the local
    clone to read, the remote (optional) builds commit URLs. A bare string is
    treated as a working tree with no remote.
    """
    specs = []
    for entry in project.get("repos") or []:
        if isinstance(entry, str):
            entry = {"working tree": entry}
        working_tree = entry.get("working tree") or entry.get("working_tree")
        if not working_tree:
            print(f"  ! skipping repo without a working tree: {entry!r}")
            continue
        remote = (entry.get("remote") or "").rstrip("/").removesuffix(".git") or None
        specs.append({"repo": Path(working_tree).name,
                      "working_tree": working_tree, "remote": remote})
    return specs


def iter_commits(repo):
    """Yield (commit_row, [file_rows]) for each commit in `repo`. Skips unreadable repos."""
    name = Path(repo).name
    proc = subprocess.run(
        ["git", "-C", str(repo), "log", "--no-color", "--numstat", "--pretty=format:" + FMT],
        capture_output=True, text=True)
    if proc.returncode != 0:
        msg = proc.stderr.strip().splitlines()[-1] if proc.stderr.strip() else "git log failed"
        print(f"  ! skipping {repo}: {msg}")
        return
    for chunk in proc.stdout.split("\x1e"):
        if not chunk.strip():
            continue
        f = chunk.split("\x1f")
        sha, an, ae, ad, cn, ce, cd, parents, subject, body = f[:10]
        numstat = f[10] if len(f) > 10 else ""
        files, ins, dels = [], 0, 0
        for line in numstat.strip().splitlines():
            if not line.strip():
                continue
            a, d, path = (line.split("\t", 2) + ["", "", ""])[:3]
            ai = int(a) if a.isdigit() else None   # "-" for binary files
            di = int(d) if d.isdigit() else None
            files.append({"repo": name, "sha": sha, "path": path,
                          "insertions": ai, "deletions": di})
            ins += ai or 0
            dels += di or 0
        commit = {
            "repo": name, "sha": sha,
            "author_name": an, "author_email": ae, "author_date": ad,
            "committer_name": cn, "committer_email": ce, "commit_date": cd,
            "parents": parents, "subject": subject, "body": (body.strip() or None),
            "files_changed": len(files), "insertions": ins, "deletions": dels,
        }
        yield commit, files


def build(db_path, specs):
    """Append an ingest of `specs` ([{repo, working_tree, remote}]) to the git
    database. Returns (ingest_id, commit_count)."""
    db = sqlite_utils.Database(db_path)   # append-only — never recreated

    # Repo metadata (remote, working tree) is mutable, not content-addressed:
    # keep the latest values so commit URLs track the current remote.
    db["repos"].insert_all(
        [{"repo": s["repo"], "remote": s["remote"], "working_tree": s["working_tree"]}
         for s in specs], pk="repo", replace=True)

    ingest_id = db["ingests"].insert(
        {"run_at": datetime.now(timezone.utc).isoformat(),
         "repos": json.dumps([s["repo"] for s in specs]),
         "commit_count": 0}, pk="id").last_pk

    commits, files, presence = [], [], []
    for s in specs:
        for commit, fs in iter_commits(s["working_tree"]):
            commits.append(commit)
            files.extend(fs)
            presence.append({"ingest_id": ingest_id, "repo": commit["repo"], "sha": commit["sha"]})

    # Commits are content-addressed: store each once, never overwrite (ignore dups).
    db["commits"].insert_all(commits, pk=("repo", "sha"), ignore=True)
    if files:
        db["commit_files"].insert_all(files, pk=("repo", "sha", "path"), ignore=True)
    db["commit_presence"].insert_all(presence, pk=("ingest_id", "repo", "sha"), ignore=True)
    db["ingests"].update(ingest_id, {"commit_count": len(commits)})

    db["commits"].create_index(["repo"], if_not_exists=True)
    db["commit_files"].create_index(["repo", "sha"], if_not_exists=True)
    if db["commits"].count and not db["commits"].detect_fts():
        db["commits"].enable_fts(["subject", "body", "author_name"], create_triggers=True)
    # Current history = the commits the latest ingest observed, each with a link
    # built from its repo's remote.
    db.create_view(
        "commits_latest",
        "SELECT c.*, "
        "CASE WHEN r.remote IS NOT NULL THEN r.remote || '/commit/' || c.sha END AS url "
        "FROM commits c "
        "JOIN commit_presence p ON p.repo = c.repo AND p.sha = c.sha "
        "LEFT JOIN repos r ON r.repo = c.repo "
        "WHERE p.ingest_id = (SELECT MAX(id) FROM ingests)",
        replace=True)
    return ingest_id, len(commits)


def fixity_check(db_path):
    """Diff the two latest ingests' commit presence per repo. Returns a report, or None."""
    db = sqlite_utils.Database(db_path)
    ids = [r["id"] for r in db["ingests"].rows_where(order_by="id")]
    if len(ids) < 2:
        return None
    prev, curr = ids[-2], ids[-1]

    def presence(ingest_id):
        out = {}
        for r in db["commit_presence"].rows_where("ingest_id = ?", [ingest_id]):
            out.setdefault(r["repo"], set()).add(r["sha"])
        return out

    old, new = presence(prev), presence(curr)
    report = {"prev_ingest": prev, "curr_ingest": curr, "repos": {}}
    for repo in sorted(set(old) | set(new)):
        o, n = old.get(repo, set()), new.get(repo, set())
        report["repos"][repo] = {"added": sorted(n - o), "dropped": sorted(o - n)}
    return report


def format_report(report):
    """Per-repo +added / -dropped; a dropped commit means history was rewritten."""
    if report is None:
        return "git fixity: first ingest — nothing to compare yet."
    lines = [f"git fixity: ingest {report['prev_ingest']} -> {report['curr_ingest']}"]
    for repo, d in report["repos"].items():
        flag = "   ! HISTORY REWRITTEN" if d["dropped"] else ""
        lines.append(f"  {repo}: +{len(d['added'])} commits, -{len(d['dropped'])}{flag}")
        for sha in d["dropped"]:
            lines.append(f"      dropped (rewrite): {sha}")
    return "\n".join(lines)


def report(db_path):
    """Print the per-day work-hours breakdown of the current history (author-local time)."""
    db = sqlite_utils.Database(db_path)
    rows = list(db.query(
        "SELECT substr(author_date,1,10) AS day, COUNT(*) AS commits, "
        "MIN(substr(author_date,12,5)) AS first, MAX(substr(author_date,12,5)) AS last, "
        "GROUP_CONCAT(DISTINCT CAST(substr(author_date,12,2) AS INTEGER)) AS hours, "
        "GROUP_CONCAT(DISTINCT repo) AS repos "
        "FROM commits_latest GROUP BY day ORDER BY day"))
    print(f"  {'date':<11}{'day':<5}{'#':>2}  {'window':<13}{'hours':<20}repos")
    total = 0
    for r in rows:
        total += r["commits"]
        weekday = datetime.fromisoformat(r["day"]).strftime("%a")
        hrs = ",".join(f"{int(h):02d}" for h in sorted(int(x) for x in r["hours"].split(",")))
        repos = r["repos"].replace("community.", "")
        print(f"  {r['day']} {weekday:<4}{r['commits']:>2}  {r['first']}-{r['last']}  {hrs:<20}{repos}")
    print(f"  total: {len(rows)} day(s), {total} commits")


def run(project):
    specs = repo_specs(project)
    if not specs:
        print(f"{project['id']}: no repositories configured; skipping")
        return
    out = project["project_folder"] / "git.sqlite"
    ingest_id, n = build(out, specs)
    print(f"{project['id']}: ingest {ingest_id}, {n} commits across {len(specs)} repo(s) -> {out}")
    print(format_report(fixity_check(out)))
    print("\nwork-hours report (current history, author-local time):")
    report(out)


def main():
    for projectid in projects.keys():
        project = projects[projectid]
        if project["source"] not in GIT_SOURCES:
            continue
        run(project)


if __name__ == "__main__":
    main()
