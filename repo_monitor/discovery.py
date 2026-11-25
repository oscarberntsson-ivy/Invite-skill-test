"""Hitta challenge-repositories och koppla dem till personer (utan lokal lagring).

* Repositories följer namnstandarden  ivy-engineering-challenge-<github-användarnamn>
  (mönstret är konfigurerbart).
* Issues som skapats med den konfigurerade templaten innehåller personens namn och
  GitHub-användarnamn. De används för att koppla ihop person ⇄ användarnamn ⇄ repository,
  så att man kan fråga "hur går det för Anna?".

Data hämtas av agenten via GitHub MCP (list_issues, search_repositories) och skickas hit
som JSON. Inget här anropar GitHub direkt.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from . import storage
from .storage import read_json, write_json
from .timeutil import parse_iso, to_iso

NO_RESPONSE = "_No response_"


def config_path() -> Path:
    return storage.home() / "discovery.json"


def default_config() -> dict:
    return {
        "owner": "IvyTechSE",
        "repo_name_pattern": r"^ivy-engineering-chall[ae]nge-(?P<username>[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)$",
        "repo_name_template": "ivy-engineering-challenge-{username}",
        "issues_repository": None,
        "automation_accounts": [],
        "issue_labels": [],
        "issue_fields": {
            "name": ["Namn", "Fullständigt namn", "Name", "Full name"],
            "github_username": ["GitHub-användarnamn", "GitHub användarnamn", "Användarnamn",
                                "GitHub username", "GitHub-username", "Username"],
        },
    }


def load_config() -> dict:
    cfg = default_config()
    data = read_json(config_path(), None)
    if data:
        fields = {**cfg["issue_fields"], **(data.get("issue_fields") or {})}
        cfg.update(data)
        cfg["issue_fields"] = fields
    return cfg


def save_config(cfg: dict) -> None:
    write_json(config_path(), cfg)


def issues_repository(cfg: dict) -> str | None:
    if cfg.get("issues_repository"):
        return cfg["issues_repository"]
    from . import issues  # undvik cirkulär import
    repo = issues.load_config().get("repository")
    return None if not repo or repo == issues.PLACEHOLDER else repo


# --------------------------------------------------------------------------
# Tolkning
# --------------------------------------------------------------------------

def _fold(text: str) -> str:
    """Skiftläges- och accentokänslig jämförelse ('Åsa' ~ 'asa')."""
    norm = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in norm if not unicodedata.combining(c)).casefold().strip()


def username_from_repo(name: str, cfg: dict) -> str | None:
    m = re.match(cfg["repo_name_pattern"], name or "", re.I)
    return m.group("username") if m else None


def parse_issue_body(body: str) -> dict[str, str | None]:
    """Läser ett issue form-svar: '### Label' följt av värdet. Klarar även 'Label: värde'-rader."""
    out: dict[str, str | None] = {}
    if not body:
        return out
    parts = re.split(r"^#{2,4}\s+(.+?)\s*$", body.replace("\r\n", "\n"), flags=re.M)
    for i in range(1, len(parts) - 1, 2):
        value = parts[i + 1].strip()
        out[parts[i].strip()] = None if value in ("", NO_RESPONSE) else value
    if not out:
        for line in body.splitlines():
            m = re.match(r"^\s*\**([^:*]{1,60}?)\**\s*:\s*\**\s*(.+?)\s*$", line)
            if m:
                out[m.group(1).strip()] = m.group(2).strip()
    return out


def _field(answers: dict, labels: list[str]):
    folded = {_fold(k): v for k, v in answers.items()}
    for label in labels:
        v = folded.get(_fold(label))
        if v:
            return v
    return None


def _clean_username(value: str | None) -> str | None:
    if not value:
        return None
    v = value.strip().splitlines()[0].strip().strip("`").lstrip("@")
    v = re.sub(r"^https?://github\.com/", "", v).strip("/")
    return v if re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})", v) else None


def person_from_issue(issue: dict, cfg: dict, repo_full: str | None) -> dict | None:
    answers = parse_issue_body(issue.get("body") or "")
    username = _clean_username(_field(answers, cfg["issue_fields"]["github_username"]))
    if not username:
        return None
    name = _field(answers, cfg["issue_fields"]["name"])
    name = name.splitlines()[0].strip() if name else None
    number = issue.get("number")
    url = issue.get("html_url") or (f"https://github.com/{repo_full}/issues/{number}"
                                    if repo_full and number else None)
    return {
        "username": username,
        "name": name,
        "issue_number": number,
        "issue_url": url,
        "issue_created_at": to_iso(parse_iso(issue.get("created_at"))),
        "issue_state": str(issue.get("state") or "").lower() or None,
    }


def _issue_list(raw):
    if raw is None:
        return None
    if isinstance(raw, dict):
        raw = raw.get("issues") or raw.get("items") or []
    return [i for i in raw if isinstance(i, dict)]


def _repo_list(raw):
    if raw is None:
        return None
    if isinstance(raw, dict):
        raw = raw.get("items") or raw.get("repositories") or []
    out = []
    for r in raw:
        if isinstance(r, str):
            owner, name = storage.parse_full_name(r)
            out.append({"owner": owner, "name": name})
        elif isinstance(r, dict):
            owner = r.get("owner")
            owner = owner.get("login") if isinstance(owner, dict) else owner
            name = r.get("name")
            if (not owner or not name) and r.get("full_name"):
                owner, name = storage.parse_full_name(r["full_name"])
            if owner and name:
                out.append({"owner": owner, "name": name, "url": r.get("html_url"),
                            "created_at": to_iso(parse_iso(r.get("created_at")))})
    return out


# --------------------------------------------------------------------------
# Personer och repositories (beräknas varje gång, sparas inte)
# --------------------------------------------------------------------------

def people(issues_raw, repos_raw, cfg: dict) -> dict:
    """Kopplar ihop person ⇄ GitHub-användarnamn ⇄ repository.

    issues_raw: svaret från list_issues i inbjudnings-repot (eller None).
    repos_raw:  svaret från search_repositories (eller None om sökning saknas).
    """
    owner = cfg["owner"]
    issues = _issue_list(issues_raw)
    repos = _repo_list(repos_raw)
    labels = {_fold(l) for l in cfg.get("issue_labels") or []}
    repo_full = issues_repository(cfg)

    found: dict[str, dict] = {}
    skipped = []
    for issue in issues or []:
        if labels:
            ilabels = {_fold(l.get("name") if isinstance(l, dict) else str(l)) for l in issue.get("labels") or []}
            if not labels & ilabels:
                continue
        p = person_from_issue(issue, cfg, repo_full)
        if p is None:
            skipped.append(issue.get("number"))
            continue
        key = p["username"].lower()
        # Senaste issuen per användare gäller (t.ex. om inbjudan gjorts om)
        if key not in found or (p["issue_created_at"] or "") >= (found[key]["issue_created_at"] or ""):
            found[key] = p

    repo_by_user: dict[str, dict] = {}
    for r in repos or []:
        u = username_from_repo(r["name"], cfg)
        if u and r["owner"].lower() == owner.lower():
            repo_by_user[u.lower()] = r

    out = []
    for key in sorted(set(found) | set(repo_by_user)):
        p = found.get(key)
        r = repo_by_user.get(key)
        username = p["username"] if p else username_from_repo(r["name"], cfg)
        repo_owner = r["owner"] if r else owner
        repo_name = r["name"] if r else cfg["repo_name_template"].format(username=username)
        out.append({
            "name": p["name"] if p else None,
            "username": username,
            "repository": f"{repo_owner}/{repo_name}",
            "repo_found": (r is not None) if repos is not None else None,
            "issue_number": p["issue_number"] if p else None,
            "issue_url": p["issue_url"] if p else None,
            "invited_at": p["issue_created_at"] if p else None,
        })
    out.sort(key=lambda x: _fold(x["name"] or x["username"]))
    return {
        "people": out,
        "issues_read": len(issues) if issues is not None else None,
        "repos_searched": repos is not None,
        "issues_without_username": [n for n in skipped if n is not None],
    }


def find(people_list: list[dict], text: str) -> list[dict]:
    """Sök på namn, GitHub-användarnamn eller repo-namn (skiftläges- och accentokänsligt)."""
    q = _fold(text).lstrip("@")
    if not q:
        return []
    exact, partial = [], []
    for p in people_list:
        hay = [_fold(h) for h in (p.get("name"), p.get("username"), p.get("repository")) if h]
        if any(q == h for h in hay):
            exact.append(p)
        elif any(q in h for h in hay) or all(any(w in h for h in hay) for w in q.split()):
            partial.append(p)
    return exact or partial


def snapshot_person(p: dict) -> dict:
    """Det objekt som ska läggas i snapshotens "person"-fält."""
    return {k: p.get(k) for k in ("name", "username", "issue_number", "issue_url", "invited_at")}


def render_people(result: dict, hits: list[dict] | None = None, query: str | None = None) -> str:
    rows = hits if hits is not None else result["people"]
    lines = []
    if query is not None:
        lines.append(f"Sökning: ”{query}” – {len(rows)} träff(ar).")
    else:
        lines.append(f"{len(rows)} kandidat(er) hittades.")
    lines.append("")
    for p in rows:
        who = p["name"] or "(namn okänt – ingen inbjudnings-issue)"
        status = {True: "", False: " – **repot hittades inte** (kanske inte skapat ännu)", None: ""}[p["repo_found"]]
        issue = f", inbjudan #{p['issue_number']}" if p.get("issue_number") else ""
        lines.append(f"- {who} (GitHub: {p['username']}): {p['repository']}{issue}{status}")
    if result.get("issues_without_username"):
        lines += ["", "Issues där inget GitHub-användarnamn kunde läsas: " +
                  ", ".join(f"#{n}" for n in result["issues_without_username"]) +
                  ". Kontrollera issue_fields i repo-monitor/discovery.json."]
    return "\n".join(lines) + "\n"
