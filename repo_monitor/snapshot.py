"""Normalisering av en snapshot med data som hämtats via GitHub MCP.

En snapshot är JSON som agenten sätter ihop av MCP-svaren. Normaliseraren
accepterar både ett förenklat format och GitHubs/MCP:s råa format, så att
agenten kan klistra in svaren nästan direkt.

Viktig konvention:  None/null betyder "kunde inte hämtas" (okänt),
medan en tom lista betyder "hämtades, men det finns inget".
"""

from __future__ import annotations

from .storage import MonitorError, parse_full_name
from .timeutil import parse_iso, to_iso


def _login(value) -> str | None:
    if isinstance(value, str):
        return value or None
    if isinstance(value, dict):
        return value.get("login") or None
    return None


def _first_line(message) -> str:
    if not message:
        return ""
    return str(message).strip().splitlines()[0].strip()


def _normalize_repo(raw: dict) -> dict:
    repo = dict(raw.get("repo") or raw.get("repository") or {})
    owner = _login(repo.get("owner"))
    name = repo.get("name")
    if (not owner or not name) and repo.get("full_name"):
        owner, name = parse_full_name(repo["full_name"])
    if (not owner or not name) and raw.get("full_name"):
        owner, name = parse_full_name(raw["full_name"])
    if not owner or not name:
        raise MonitorError(
            "Snapshoten saknar repository-namn. Ange t.ex. "
            '"repo": {"owner": "min-org", "name": "mitt-projekt"}.'
        )
    return {
        "owner": owner,
        "name": name,
        "url": repo.get("html_url") or repo.get("url") or f"https://github.com/{owner}/{name}",
        "created_at": to_iso(parse_iso(repo.get("created_at"))),
        "pushed_at": to_iso(parse_iso(repo.get("pushed_at"))),
        "default_branch": repo.get("default_branch") or None,
        "description": repo.get("description") or None,
    }


def _normalize_commit(raw: dict, branch: str | None) -> dict | None:
    if not isinstance(raw, dict):
        return None
    sha = raw.get("sha")
    if not sha:
        return None
    inner = raw.get("commit") if isinstance(raw.get("commit"), dict) else {}
    inner_author = inner.get("author") if isinstance(inner.get("author"), dict) else {}

    author = raw.get("author")
    login = raw.get("author_login") or _login(author)
    name = raw.get("author_name") or inner_author.get("name")
    if isinstance(author, str) and not raw.get("author_login"):
        # Förenklat format: "author": "anna"
        login = author
    email = raw.get("author_email") or inner_author.get("email")

    date = raw.get("date") or inner_author.get("date")
    if not date and isinstance(inner.get("committer"), dict):
        date = inner["committer"].get("date")

    files = []
    for f in raw.get("files") or []:
        if isinstance(f, str):
            files.append(f)
        elif isinstance(f, dict) and f.get("filename"):
            files.append(f["filename"])

    parents = raw.get("parents")
    parent_count = len(parents) if isinstance(parents, list) else raw.get("parent_count")

    branches = list(raw.get("branches") or [])
    if branch and branch not in branches:
        branches.append(branch)

    return {
        "sha": sha,
        "message": (raw.get("message") or inner.get("message") or "").strip(),
        "author_login": login,
        "author_name": name,
        "author_email": email,
        "date": to_iso(parse_iso(date)),
        "files": files,
        "parent_count": parent_count,
        "branches": branches,
    }


def _merge_commit(target: dict, other: dict) -> None:
    for b in other["branches"]:
        if b not in target["branches"]:
            target["branches"].append(b)
    for key in ("author_login", "author_name", "author_email", "date", "parent_count"):
        if not target.get(key) and other.get(key):
            target[key] = other[key]
    if not target.get("files") and other.get("files"):
        target["files"] = other["files"]
    if len(other.get("message") or "") > len(target.get("message") or ""):
        target["message"] = other["message"]


def _normalize_commits(raw: dict):
    has_list = "commits" in raw
    has_map = "commits_by_branch" in raw
    if not has_list and not has_map:
        return None
    if (has_list and raw["commits"] is None) and (not has_map or raw["commits_by_branch"] is None):
        return None

    by_sha: dict[str, dict] = {}
    order: list[str] = []

    def add(item, branch):
        c = _normalize_commit(item, branch)
        if c is None:
            return
        if c["sha"] in by_sha:
            _merge_commit(by_sha[c["sha"]], c)
        else:
            by_sha[c["sha"]] = c
            order.append(c["sha"])

    for item in raw.get("commits") or []:
        add(item, None)
    for branch, items in (raw.get("commits_by_branch") or {}).items():
        for item in items or []:
            add(item, branch)
    return [by_sha[s] for s in order]


def _normalize_branches(raw: dict):
    if raw.get("branches") is None:
        return None
    out = []
    for b in raw["branches"]:
        if isinstance(b, str):
            out.append({"name": b, "sha": None})
        elif isinstance(b, dict) and b.get("name"):
            sha = b.get("sha")
            if not sha and isinstance(b.get("commit"), dict):
                sha = b["commit"].get("sha")
            out.append({"name": b["name"], "sha": sha})
    return out


def _ref(value):
    if isinstance(value, dict):
        return value.get("ref")
    return value


def _normalize_prs(raw: dict):
    key = "pull_requests" if "pull_requests" in raw else ("pulls" if "pulls" in raw else None)
    if key is None or raw[key] is None:
        return None
    out = []
    for pr in raw[key]:
        if not isinstance(pr, dict) or pr.get("number") is None:
            continue
        merged_at = pr.get("merged_at")
        merged = bool(merged_at) or pr.get("merged") is True
        state = str(pr.get("state") or "").lower()
        if merged:
            state = "merged"
        elif state not in ("open", "closed"):
            state = "open" if not pr.get("closed_at") else "closed"
        out.append({
            "number": int(pr["number"]),
            "title": pr.get("title") or "",
            "state": state,
            "author": _login(pr.get("user")) or _login(pr.get("author")),
            "created_at": to_iso(parse_iso(pr.get("created_at"))),
            "closed_at": to_iso(parse_iso(pr.get("closed_at"))),
            "merged_at": to_iso(parse_iso(merged_at)),
            "merged_by": _login(pr.get("merged_by")),
            "base": _ref(pr.get("base")),
            "head": _ref(pr.get("head")),
            "url": pr.get("html_url") or pr.get("url"),
            "draft": bool(pr.get("draft")),
        })
    out.sort(key=lambda p: p["number"])
    return out


def normalize(raw: dict) -> dict:
    """Returnerar en normaliserad snapshot (se docs/snapshot-format.md)."""
    if not isinstance(raw, dict):
        raise MonitorError("Snapshoten måste vara ett JSON-objekt.")
    repo = _normalize_repo(raw)

    access = raw.get("access") or {"ok": True}
    if not isinstance(access, dict):
        access = {"ok": bool(access)}
    access = {"ok": bool(access.get("ok", True)), "error": access.get("error")}

    errors = []
    for e in raw.get("errors") or []:
        if isinstance(e, str):
            errors.append({"what": "okänd del", "message": e})
        elif isinstance(e, dict):
            errors.append({"what": e.get("what") or "okänd del", "message": e.get("message") or ""})

    if not access["ok"]:
        return {
            "repo": repo,
            "fetched_at": to_iso(parse_iso(raw.get("fetched_at"))),
            "access": access,
            "branches": None,
            "commits": None,
            "pull_requests": None,
            "errors": errors,
        }

    return {
        "repo": repo,
        "fetched_at": to_iso(parse_iso(raw.get("fetched_at"))),
        "access": access,
        "branches": _normalize_branches(raw),
        "commits": _normalize_commits(raw),
        "pull_requests": _normalize_prs(raw),
        "errors": errors,
    }


def first_line(message) -> str:
    return _first_line(message)
