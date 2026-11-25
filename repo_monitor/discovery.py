"""Hitta challenge-repositories och koppla dem till personer.

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
from .storage import MonitorError, read_json, write_json
from .timeutil import now_utc, parse_iso, to_iso

NO_RESPONSE = "_No response_"


def config_path() -> Path:
    return storage.home() / "discovery.json"


def default_config() -> dict:
    return {
        "owner": "IvyTechSE",
        "repo_name_pattern": r"^ivy-engineering-chall[ae]nge-(?P<username>[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)$",
        "repo_name_template": "ivy-engineering-challenge-{username}",
        "issues_repository": None,
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
# Synkronisering till registret
# --------------------------------------------------------------------------

def sync(registry: dict, issues_raw, repos_raw, cfg: dict) -> dict:
    """Uppdaterar registret. Returnerar en sammanställning av vad som hände."""
    owner = cfg["owner"]
    issues = _issue_list(issues_raw)
    repos = _repo_list(repos_raw)
    labels = {_fold(l) for l in cfg.get("issue_labels") or []}
    repo_full = issues_repository(cfg)

    people: dict[str, dict] = {}
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
        # Senaste issuen per användare vinner (t.ex. om den skickats in igen)
        if key not in people or (p["issue_created_at"] or "") >= (people[key]["issue_created_at"] or ""):
            people[key] = p

    found_repos: dict[str, dict] = {}
    for r in repos or []:
        u = username_from_repo(r["name"], cfg)
        if u and r["owner"].lower() == owner.lower():
            found_repos[u.lower()] = r

    added, updated, unverified = [], [], []
    for key in sorted(set(people) | set(found_repos)):
        p = people.get(key)
        r = found_repos.get(key)
        username = (p or {}).get("username") or username_from_repo(r["name"], cfg)
        name = r["name"] if r else cfg["repo_name_template"].format(username=username)
        entry_owner = r["owner"] if r else owner
        verified = r is not None if repos is not None else None
        fields = {
            "github_username": username,
            "invited_contributors": [username],
            "source": "discovered",
            "repo_verified": verified,
        }
        if r and r.get("url"):
            fields["url"] = r["url"]
        if r and r.get("created_at"):
            fields["created_at"] = r["created_at"]
        if p:
            fields.update({
                "person_name": p["name"],
                "invitation_issue": p["issue_number"],
                "invitation_issue_url": p["issue_url"],
                "invited_at": p["issue_created_at"],
            })
        existing = storage.find_entry(registry, entry_owner, name)
        if existing is None or existing.get("source") in (None, "discovered") \
                or existing.get("project_name") in (None, existing.get("name")):
            fields["project_name"] = (p and p["name"]) or username
        entry, created = storage.upsert_entry(registry, entry_owner, name, **fields)
        (added if created else updated).append(f"{entry_owner}/{name}")
        if verified is False:
            unverified.append(f"{entry_owner}/{name}")

    registry["last_discovery_at"] = to_iso(now_utc())
    return {
        "issues_read": len(issues) if issues is not None else None,
        "repos_read": len(repos) if repos is not None else None,
        "people": len(people),
        "added": added,
        "updated": updated,
        "repos_not_found": unverified,
        "issues_without_username": [n for n in skipped if n is not None],
        "repos_without_issue": sorted(f"{r['owner']}/{r['name']}" for k, r in found_repos.items()
                                      if k not in people),
    }


def render_sync(result: dict) -> str:
    lines = ["## Synkronisering av challenge-repositories", ""]
    lines.append(f"- Issues lästa: {'okänt (hämtades inte)' if result['issues_read'] is None else result['issues_read']}")
    lines.append(f"- Repositories lästa: {'inte sökta' if result['repos_read'] is None else result['repos_read']}")
    lines.append(f"- Personer identifierade från issues: {result['people']}")
    lines.append(f"- Nya i registret: {len(result['added'])}" + (f" ({', '.join(result['added'])})" if result["added"] else ""))
    lines.append(f"- Uppdaterade: {len(result['updated'])}")
    if result["repos_not_found"]:
        lines += ["", "**Repositories som borde finnas enligt en issue, men som inte hittades:**"]
        lines += [f"- {r} (GitHub Action kan ha misslyckats eller inte körts ännu)" for r in result["repos_not_found"]]
    if result["repos_without_issue"]:
        lines += ["", "**Repositories utan matchande issue** (personens namn är okänt, användarnamnet visas):"]
        lines += [f"- {r}" for r in result["repos_without_issue"]]
    if result["issues_without_username"]:
        lines += ["", "**Issues där inget GitHub-användarnamn kunde läsas:** " +
                  ", ".join(f"#{n}" for n in result["issues_without_username"]),
                  "Kontrollera `issue_fields` i repo-monitor/discovery.json."]
    return "\n".join(lines) + "\n"


def find(registry: dict, text: str) -> list[dict]:
    """Sök i registret på personnamn, användarnamn, projektnamn eller repo-namn."""
    q = _fold(text).lstrip("@")
    if not q:
        return []
    hits = []
    for e in registry["repositories"]:
        hay = [e.get("person_name"), e.get("github_username"), e.get("project_name"),
               e.get("name"), f"{e['owner']}/{e['name']}"]
        hay += e.get("invited_contributors") or []
        folded = [_fold(h) for h in hay if h]
        if any(q == h for h in folded):
            hits.append((0, e))
        elif any(q in h for h in folded) or all(any(w in h for h in folded) for w in q.split()):
            hits.append((1, e))
    hits.sort(key=lambda x: (x[0], x[1].get("project_name") or ""))
    return [e for _, e in hits]


def register_invitation(registry: dict, draft: dict, cfg: dict | None = None) -> dict | None:
    """Registrerar kandidatens (förväntade) repository direkt när beställnings-issuen skapats.

    Läser namn och användarnamn ur issuens beskrivning med samma regler som `sync`.
    Returnerar registerposten, eller None om inget användarnamn kunde läsas.
    """
    cfg = cfg or load_config()
    payload = draft.get("payload") or {}
    issue = {"number": draft.get("issue_number"), "html_url": draft.get("issue_url"),
             "body": payload.get("body"), "created_at": draft.get("submitted_at"), "state": "open"}
    person = person_from_issue(issue, cfg, draft.get("repository"))
    if person is None:
        return None
    name = cfg["repo_name_template"].format(username=person["username"])
    existing = storage.find_entry(registry, cfg["owner"], name)
    fields = {
        "github_username": person["username"],
        "invited_contributors": [person["username"]],
        "person_name": person["name"],
        "invitation_issue": person["issue_number"],
        "invitation_issue_url": person["issue_url"],
        "invited_at": person["issue_created_at"],
        "source": (existing or {}).get("source") or "invitation",
    }
    if existing is None or existing.get("project_name") in (None, existing.get("name")):
        fields["project_name"] = person["name"] or person["username"]
    entry, _ = storage.upsert_entry(registry, cfg["owner"], name, **fields)
    return entry
