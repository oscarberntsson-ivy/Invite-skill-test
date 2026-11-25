"""Analys av en normaliserad snapshot: status, contributors, händelser och förändringar.

Principer:
* Hitta aldrig på aktivitet. Allt härleds ur GitHub-data i snapshoten.
* Skilj på "okänt" (data saknas) och "ingen aktivitet" (data finns, men är tom).
* Skilj på händelsetyperna: repository skapat, commit, push, pull request skapad,
  pull request mergad, pull request stängd.
"""

from __future__ import annotations

from datetime import timedelta

from .snapshot import first_line
from .timeutil import parse_iso, to_iso

# Commits som görs inom detta fönster efter att repot skapats räknas som
# automatisk uppsättning (t.ex. README från repo-flödet), inte som kodbidrag.
SETUP_WINDOW = timedelta(minutes=10)

# Kodstatus
INAKTIVT = "INAKTIVT"
PABORJAT = "PÅBÖRJAT"
AKTIVT = "AKTIVT"
OKANT = "OKÄNT"
EJ_TILLGANGLIGT = "EJ TILLGÄNGLIGT"

# Granskningsstatus
UNDER_GRANSKNING = "UNDER GRANSKNING"
MERGAT = "MERGAT"
INGA_PR = "INGA PULL REQUESTS"

# Händelsetyper (får inte blandas ihop)
EV_REPO_CREATED = "repo_created"
EV_SETUP_COMMIT = "setup_commit"
EV_COMMIT = "commit"
EV_MERGE_COMMIT = "merge_commit"
EV_PUSH = "push"
EV_PR_OPENED = "pr_opened"
EV_PR_MERGED = "pr_merged"
EV_PR_CLOSED = "pr_closed"


def contributor_key(login, name, email) -> str:
    if login:
        return login.lower()
    if name:
        return f"namn:{name.lower()}"
    if email:
        return f"epost:{email.lower()}"
    return "okänd"


def contributor_display(login, name) -> str:
    if name and login and name.lower() != login.lower():
        return f"{name} ({login})"
    return name or login or "Okänd person"


def _date_key(c):
    return c.get("date") or ""


def classify_commits(snapshot: dict, automation_accounts) -> tuple[list, list, list]:
    """Delar upp commits i (kodbidrag, uppsättning, merge-commits)."""
    commits = snapshot.get("commits")
    if commits is None:
        return [], [], []
    auto = {a.lower() for a in automation_accounts or []}
    created = parse_iso(snapshot["repo"].get("created_at"))

    ordered = sorted(commits, key=_date_key)
    oldest_sha = ordered[0]["sha"] if ordered else None

    contrib, setup, merges = [], [], []
    for c in ordered:
        login = (c.get("author_login") or "").lower()
        when = parse_iso(c.get("date"))
        is_setup = bool(login and login in auto)
        if (
            not is_setup
            and c["sha"] == oldest_sha
            and created is not None
            and when is not None
            and when <= created + SETUP_WINDOW
        ):
            is_setup = True
        if is_setup:
            setup.append(c)
        elif (c.get("parent_count") or 0) >= 2:
            merges.append(c)
        else:
            contrib.append(c)
    return contrib, setup, merges


def _build_contributors(contrib_commits: list) -> list[dict]:
    people: dict[str, dict] = {}
    for c in contrib_commits:
        key = contributor_key(c.get("author_login"), c.get("author_name"), c.get("author_email"))
        p = people.setdefault(key, {
            "key": key,
            "login": c.get("author_login"),
            "name": c.get("author_name"),
            "display": contributor_display(c.get("author_login"), c.get("author_name")),
            "commits": 0,
            "first_date": None,
            "last_date": None,
            "branches": [],
            "messages": [],
            "files": [],
        })
        p["commits"] += 1
        d = c.get("date")
        if d and (p["first_date"] is None or d < p["first_date"]):
            p["first_date"] = d
        if d and (p["last_date"] is None or d > p["last_date"]):
            p["last_date"] = d
        for b in c.get("branches") or []:
            if b not in p["branches"]:
                p["branches"].append(b)
        msg = first_line(c.get("message"))
        if msg:
            p["messages"].append({"date": d, "message": msg, "sha": c["sha"][:7]})
        for f in c.get("files") or []:
            if f not in p["files"]:
                p["files"].append(f)
    out = list(people.values())
    for p in out:
        p["messages"].sort(key=lambda m: m["date"] or "", reverse=True)
    out.sort(key=lambda p: (-(p["commits"]), p["display"].lower()))
    return out


def code_status(contrib_commits, commits_known: bool) -> str:
    if not commits_known:
        return OKANT
    if not contrib_commits:
        return INAKTIVT
    authors = {contributor_key(c.get("author_login"), c.get("author_name"), c.get("author_email"))
               for c in contrib_commits}
    days = {c["date"][:10] for c in contrib_commits if c.get("date")}
    if len(authors) >= 2 or len(days) >= 2:
        return AKTIVT
    return PABORJAT


def review_status(prs) -> list[str]:
    if prs is None:
        return [OKANT]
    flags = []
    if any(p["state"] == "open" for p in prs):
        flags.append(UNDER_GRANSKNING)
    if any(p["state"] == "merged" for p in prs):
        flags.append(MERGAT)
    return flags or [INGA_PR]


def _push_is_activity(repo: dict) -> bool:
    created = parse_iso(repo.get("created_at"))
    pushed = parse_iso(repo.get("pushed_at"))
    if pushed is None:
        return False
    if created is None:
        return True
    return pushed > created + SETUP_WINDOW


def _events(snapshot, contrib, setup, merges) -> list[dict]:
    repo = snapshot["repo"]
    ev = []
    if repo.get("created_at"):
        ev.append({"type": EV_REPO_CREATED, "date": repo["created_at"], "who": None})
    for c in setup:
        ev.append({"type": EV_SETUP_COMMIT, "date": c.get("date"), "who": None,
                   "message": first_line(c.get("message")), "branches": c.get("branches", [])})
    for c in contrib:
        ev.append({"type": EV_COMMIT, "date": c.get("date"),
                   "who": contributor_display(c.get("author_login"), c.get("author_name")),
                   "message": first_line(c.get("message")), "branches": c.get("branches", []),
                   "sha": c["sha"][:7]})
    for c in merges:
        ev.append({"type": EV_MERGE_COMMIT, "date": c.get("date"),
                   "who": contributor_display(c.get("author_login"), c.get("author_name")),
                   "message": first_line(c.get("message")), "branches": c.get("branches", [])})
    if _push_is_activity(repo):
        ev.append({"type": EV_PUSH, "date": repo["pushed_at"], "who": None})
    for pr in snapshot.get("pull_requests") or []:
        ev.append({"type": EV_PR_OPENED, "date": pr.get("created_at"), "who": pr.get("author"),
                   "number": pr["number"], "title": pr["title"], "base": pr.get("base"),
                   "head": pr.get("head")})
        if pr["state"] == "merged":
            ev.append({"type": EV_PR_MERGED, "date": pr.get("merged_at"),
                       "who": pr.get("merged_by"), "number": pr["number"], "title": pr["title"],
                       "base": pr.get("base")})
        elif pr["state"] == "closed":
            ev.append({"type": EV_PR_CLOSED, "date": pr.get("closed_at"), "who": None,
                       "number": pr["number"], "title": pr["title"]})
    ev.sort(key=lambda e: e.get("date") or "", reverse=True)
    return ev


def _last_activity(events) -> dict | None:
    """Senaste händelse som är verklig aktivitet (inte skapande/uppsättning)."""
    for e in events:  # redan sorterad, nyast först
        if e["type"] in (EV_REPO_CREATED, EV_SETUP_COMMIT):
            continue
        if e.get("date"):
            return e
    return None


def analyze(snapshot: dict, automation_accounts, now, since=None) -> dict:
    """Analyserar en snapshot. `since` (datum) räknar commits från och med den tidpunkten."""
    repo = snapshot["repo"]
    person = snapshot.get("person") or {}
    username = person.get("username")
    project = {
        "owner": repo["owner"],
        "name": repo["name"],
        "full_name": f"{repo['owner']}/{repo['name']}",
        "project_name": person.get("name") or username or repo["name"],
        "url": repo.get("url"),
        "created_at": repo.get("created_at"),
        "default_branch": repo.get("default_branch"),
        "invited_contributors": [username] if username else [],
        "person_name": person.get("name"),
        "github_username": username,
        "invitation_issue": person.get("issue_number"),
        "invitation_issue_url": person.get("issue_url"),
        "invited_at": person.get("invited_at"),
    }
    checked_at = to_iso(now)

    if not snapshot["access"]["ok"]:
        return {
            "project": project,
            "checked_at": checked_at,
            "access": snapshot["access"],
            "code_status": EJ_TILLGANGLIGT,
            "review_status": [EJ_TILLGANGLIGT],
            "data_gaps": ["hela repositoryt"],
            "errors": snapshot.get("errors") or [],
        }

    commits_known = snapshot.get("commits") is not None
    contrib, setup, merges = classify_commits(snapshot, automation_accounts)
    contributors = _build_contributors(contrib)
    person, uname = project["person_name"], (project["github_username"] or "").lower()
    if person and uname:
        for p in contributors:
            if (p["login"] or "").lower() == uname:
                p["display"] = f"{person} ({p['login']})"
    prs = snapshot.get("pull_requests")
    branches = snapshot.get("branches")
    events = _events(snapshot, contrib, setup, merges)
    last = _last_activity(events)

    last_contrib_commit = max(contrib, key=_date_key) if contrib else None
    display_by_key = {p["key"]: p["display"] for p in contributors}
    default_branch = repo.get("default_branch")
    side_branches = []
    if branches is not None:
        for b in branches:
            if b["name"] == default_branch:
                continue
            n = sum(1 for c in contrib if b["name"] in (c.get("branches") or []))
            side_branches.append({"name": b["name"], "commits": n})

    on_default = [c for c in contrib if default_branch and default_branch in (c.get("branches") or [])]

    data_gaps = []
    if not commits_known:
        data_gaps.append("commits")
    if prs is None:
        data_gaps.append("pull requests")
    if branches is None:
        data_gaps.append("branches")
    if not repo.get("created_at"):
        data_gaps.append("skapandedatum")

    invited = project["invited_contributors"]
    active_logins = {(p["login"] or "").lower() for p in contributors}
    invited_inactive = [i for i in invited if i.lower() not in active_logins] if commits_known else []

    since_iso = to_iso(parse_iso(since)) if since else None
    since_commits = ([c for c in contrib if (c.get("date") or "") >= since_iso]
                     if since_iso and commits_known else None)

    return {
        "project": project,
        "checked_at": checked_at,
        "access": snapshot["access"],
        "errors": snapshot.get("errors") or [],
        "data_gaps": data_gaps,
        "code_status": code_status(contrib, commits_known),
        "review_status": review_status(prs),
        "commit_count": len(contrib) if commits_known else None,
        "setup_commit_count": len(setup) if commits_known else None,
        "merge_commit_count": len(merges) if commits_known else None,
        "commits_on_default_branch": len(on_default) if commits_known else None,
        "contributors": contributors if commits_known else None,
        "contributor_count": len(contributors) if commits_known else None,
        "invited_inactive": invited_inactive,
        "last_activity": last,
        "last_contributor": (display_by_key.get(contributor_key(
                                 last_contrib_commit.get("author_login"), last_contrib_commit.get("author_name"),
                                 last_contrib_commit.get("author_email")))
                             if last_contrib_commit else None),
        "last_push": repo.get("pushed_at") if _push_is_activity(repo) else None,
        "branches": [b["name"] for b in branches] if branches is not None else None,
        "side_branches": side_branches if branches is not None else None,
        "default_branch": default_branch,
        "open_prs": [p for p in prs if p["state"] == "open"] if prs is not None else None,
        "merged_prs": [p for p in prs if p["state"] == "merged"] if prs is not None else None,
        "closed_prs": [p for p in prs if p["state"] == "closed"] if prs is not None else None,
        "events": events,
        "since": since_iso,
        "since_commits": since_commits,
    }
