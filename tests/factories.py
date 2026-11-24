"""Hjälpfunktioner för att bygga mockad GitHub-data i samma form som GitHub MCP returnerar."""

import itertools

_sha = itertools.count(1)

CREATED = "2026-11-01T09:00:00Z"


def sha():
    return f"{next(_sha):040x}"


def repo(name="projekt", owner="testorg", created_at=CREATED, pushed_at=None, default_branch="main"):
    return {
        "owner": {"login": owner},
        "name": name,
        "full_name": f"{owner}/{name}",
        "html_url": f"https://github.com/{owner}/{name}",
        "created_at": created_at,
        "pushed_at": pushed_at or created_at,
        "default_branch": default_branch,
    }


def commit(login, date, message="Uppdatera kod", name=None, parents=1, files=None, sha_value=None):
    """Commit i GitHub/MCP-råformat (som list_commits/get_commit)."""
    c = {
        "sha": sha_value or sha(),
        "commit": {
            "message": message,
            "author": {"name": name or login.capitalize(), "email": f"{login}@example.com", "date": date},
            "committer": {"name": name or login.capitalize(), "date": date},
        },
        "author": {"login": login},
        "parents": [{"sha": "x"}] * parents,
    }
    if files:
        c["files"] = [{"filename": f} for f in files]
    return c


def setup_commit(date="2026-11-01T09:00:30Z"):
    return commit("repo-bot", date, message="Initial commit")


def pr(number, title, login, state="open", created_at="2026-11-10T10:00:00Z",
       merged_at=None, closed_at=None, base="main", head="feature"):
    return {
        "number": number,
        "title": title,
        "state": "closed" if (merged_at or closed_at) else state,
        "user": {"login": login},
        "created_at": created_at,
        "merged_at": merged_at,
        "closed_at": closed_at or merged_at,
        "base": {"ref": base},
        "head": {"ref": head},
        "html_url": f"https://github.com/testorg/projekt/pull/{number}",
    }


def snapshot(repo_info, commits_by_branch=None, prs=None, branches=None, fetched_at="2026-11-24T12:00:00Z"):
    commits_by_branch = commits_by_branch if commits_by_branch is not None else {"main": []}
    if branches is None:
        branches = [
            {"name": b, "commit": {"sha": (cs[0]["sha"] if cs else "0" * 40)}}
            for b, cs in commits_by_branch.items()
        ]
    return {
        "fetched_at": fetched_at,
        "access": {"ok": True},
        "repo": repo_info,
        "branches": branches,
        "commits_by_branch": commits_by_branch,
        "pull_requests": prs if prs is not None else [],
        "errors": [],
    }


def inaccessible(name="hemligt", owner="testorg", error="404 Not Found"):
    return {
        "fetched_at": "2026-11-24T12:00:00Z",
        "access": {"ok": False, "error": error},
        "repo": {"owner": owner, "name": name},
    }
