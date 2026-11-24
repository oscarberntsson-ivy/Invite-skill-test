"""Kommandoradsgränssnitt: python3 -m repo_monitor <kommando>.

Kommandon:
  registry list|show|add|remove|set-automation   Hantera registret över projekt
  template OWNER/REPO                            Skriv ut en tom snapshot-mall
  analyze SNAPSHOT [--view V] [--save]           Analysera ett repository
  overview SNAPSHOT...                           Översikt över flera repositories
  state show OWNER/REPO                          Visa sparad historik
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import analysis as A
from . import discovery, issues, render, storage
from .snapshot import normalize
from .storage import MonitorError
from .timeutil import fmt_date, now_utc, parse_iso, to_iso

VIEWS = ("status", "activity", "contributors", "changes", "report")
# Vyer som räknas som en "kontroll" och därför uppdaterar historiken som standard.
SAVING_VIEWS = {"changes", "report"}


def _print(text: str) -> None:
    sys.stdout.write(text if text.endswith("\n") else text + "\n")


def _load_snapshot(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        raise MonitorError(f"Snapshot-filen {path} finns inte.")
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise MonitorError(
            f"Snapshot-filen {path} innehåller ogiltig JSON (rad {exc.lineno}, kolumn {exc.colno}): {exc.msg}"
        ) from exc
    return normalize(raw)


def _run_analysis(snapshot: dict, registry: dict, now):
    repo = snapshot["repo"]
    entry = storage.find_entry(registry, repo["owner"], repo["name"])
    prev = storage.load_state(repo["owner"], repo["name"])
    result = A.analyze(snapshot, entry, prev, registry.get("automation_accounts"), now)
    return result, entry, prev


def _persist(snapshot, result, entry, prev, registry, markdown, now) -> None:
    repo = snapshot["repo"]
    state = A.build_state(result, snapshot, prev)
    if markdown is not None and result["access"]["ok"]:
        path = storage.save_report(repo["owner"], repo["name"], markdown, now)
        try:
            state["last_report"] = str(path.relative_to(storage.home()))
        except ValueError:
            state["last_report"] = str(path)
    storage.save_state(repo["owner"], repo["name"], state)
    if entry is not None and result["access"]["ok"]:
        if repo.get("created_at"):
            entry["created_at"] = repo["created_at"]
        if repo.get("url"):
            entry["url"] = repo["url"]
        if result.get("contributors") is not None:
            entry["contributors"] = [p["login"] or p["display"] for p in result["contributors"]]
        last = result.get("last_activity")
        entry["last_activity"] = last["date"] if last else entry.get("last_activity")
        entry["last_checked_at"] = result["checked_at"]
        storage.save_registry(registry)


def _json_safe(result: dict) -> dict:
    return {k: v for k, v in result.items() if not k.startswith("_")}


# --------------------------------------------------------------------------
# Kommandon
# --------------------------------------------------------------------------

def cmd_analyze(args) -> int:
    snapshot = _load_snapshot(args.snapshot)
    registry = storage.load_registry()
    now = parse_iso(args.now) if args.now else now_utc()
    result, entry, prev = _run_analysis(snapshot, registry, now)
    markdown = render.render(result, args.view)
    save = args.save if args.save is not None else args.view in SAVING_VIEWS
    if save:
        _persist(snapshot, result, entry, prev, registry,
                 markdown if args.view == "report" else None, now)
    if args.format == "json":
        _print(json.dumps(_json_safe(result), ensure_ascii=False, indent=2))
    else:
        _print(markdown)
        if save:
            _print("\n*Kontrollen har sparats. Nästa kontroll jämförs mot denna.*")
    return 0


def cmd_overview(args) -> int:
    registry = storage.load_registry()
    now = parse_iso(args.now) if args.now else now_utc()
    analyses, seen = [], set()
    to_persist = []
    for path in args.snapshots:
        snapshot = _load_snapshot(path)
        result, entry, prev = _run_analysis(snapshot, registry, now)
        analyses.append(result)
        seen.add(storage.repo_key(snapshot["repo"]["owner"], snapshot["repo"]["name"]))
        to_persist.append((snapshot, result, entry, prev))
    unchecked = [e for e in registry["repositories"]
                 if storage.repo_key(e["owner"], e["name"]) not in seen]
    markdown = render.render_overview(analyses, unchecked, now)
    save = args.save if args.save is not None else True
    if save:
        for snapshot, result, entry, prev in to_persist:
            _persist(snapshot, result, entry, prev, registry, None, now)
    if args.format == "json":
        _print(json.dumps({"checked_at": to_iso(now),
                           "projects": [_json_safe(a) for a in analyses],
                           "unchecked": unchecked}, ensure_ascii=False, indent=2))
    else:
        _print(markdown)
    return 0


def cmd_template(args) -> int:
    owner, name = storage.parse_full_name(args.repo)
    template = {
        "fetched_at": to_iso(now_utc()),
        "access": {"ok": True, "error": None},
        "repo": {"owner": owner, "name": name, "html_url": f"https://github.com/{owner}/{name}",
                 "created_at": None, "pushed_at": None, "default_branch": "main"},
        "branches": [],
        "commits_by_branch": {"main": []},
        "pull_requests": [],
        "errors": [],
    }
    _print(json.dumps(template, ensure_ascii=False, indent=2))
    return 0


def cmd_registry(args) -> int:
    registry = storage.load_registry()
    action = args.action
    if action == "list":
        repos = registry["repositories"]
        if args.format == "json":
            _print(json.dumps(registry, ensure_ascii=False, indent=2))
            return 0
        if not repos:
            _print("Registret är tomt. Lägg till ett projekt med:\n"
                   "  python3 -m repo_monitor registry add ägare/namn")
            return 0
        _print(f"{len(repos)} registrerade projekt:\n")
        for e in repos:
            last = fmt_date(e["last_activity"]) if e.get("last_activity") else "ingen känd"
            created = fmt_date(e["created_at"]) if e.get("created_at") else "okänt"
            people = ", ".join(e.get("contributors") or []) or "inga ännu"
            person = f" – {e['person_name']}" if e.get("person_name") else ""
            _print(f"- {e['owner']}/{e['name']} ({e.get('project_name') or e['name']}){person}\n"
                   f"    URL: {e.get('url')}\n    Skapat: {created} · Senaste aktivitet: {last}\n"
                   f"    Contributors: {people}"
                   + (f"\n    Inbjudna: {', '.join(e['invited_contributors'])}" if e.get("invited_contributors") else ""))
        if registry.get("automation_accounts"):
            _print("\nAutomationskonton (räknas inte som contributors): "
                   + ", ".join(registry["automation_accounts"]))
        return 0

    if action == "set-automation":
        accounts = [a.strip() for a in (args.repo or "").split(",") if a.strip()]
        registry["automation_accounts"] = accounts
        storage.save_registry(registry)
        _print("Automationskonton: " + (", ".join(accounts) or "(inga)"))
        return 0

    if action == "find":
        hits = discovery.find(registry, args.repo)
        if args.format == "json":
            _print(json.dumps(hits, ensure_ascii=False, indent=2))
        elif not hits:
            _print(f"Inget registrerat projekt matchar ”{args.repo}”.")
        else:
            for e in hits:
                who = e.get("person_name") or e.get("github_username") or e.get("project_name")
                _print(f"- {who}: {e['owner']}/{e['name']}"
                       + (f" (GitHub: {e['github_username']})" if e.get("github_username") else ""))
        return 0

    owner, name = storage.parse_full_name(args.repo)
    if action == "show":
        entry = storage.find_entry(registry, owner, name)
        if entry is None:
            raise MonitorError(f"{owner}/{name} finns inte i registret.")
        _print(json.dumps(entry, ensure_ascii=False, indent=2))
        return 0
    if action == "remove":
        if not storage.remove_entry(registry, owner, name):
            raise MonitorError(f"{owner}/{name} finns inte i registret.")
        storage.save_registry(registry)
        _print(f"{owner}/{name} togs bort ur registret (historiken i repo-monitor/state/ finns kvar).")
        return 0
    if action == "add":
        invited = [i.strip().lstrip("@") for i in (args.invited or "").split(",") if i.strip()]
        created_at = to_iso(parse_iso(args.created_at)) if args.created_at else None
        if args.created_at and created_at is None:
            raise MonitorError(f"Ogiltigt datum: {args.created_at}. Använd t.ex. 2026-11-24 eller 2026-11-24T10:00:00Z.")
        entry, created = storage.upsert_entry(
            registry, owner, name,
            project_name=args.project_name, url=args.url, created_at=created_at,
            invited_contributors=invited or None, source=args.source,
            invitation_issue=args.issue,
        )
        storage.save_registry(registry)
        _print(("Registrerade " if created else "Uppdaterade ") + f"{owner}/{name}.")
        return 0
    raise MonitorError(f"Okänd registeråtgärd: {action}")


def cmd_state(args) -> int:
    owner, name = storage.parse_full_name(args.repo)
    state = storage.load_state(owner, name)
    if state is None:
        _print(f"Ingen historik finns för {owner}/{name}. Nästa kontroll blir en baslinje.")
        return 0
    _print(json.dumps(state, ensure_ascii=False, indent=2))
    return 0


def _read_json_arg(path, what):
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        raise MonitorError(f"{what}-filen {path} finns inte.")
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise MonitorError(f"{what}-filen {path} innehåller ogiltig JSON (rad {exc.lineno}): {exc.msg}") from exc


def _load_template(path):
    cfg, _, _ = issues.require_config()
    p = Path(path)
    if not p.exists():
        raise MonitorError(f"Template-filen {path} finns inte. Hämta {cfg['template_path']} via GitHub MCP först.")
    return issues.parse_template(p.read_text(encoding="utf-8"), cfg["template_path"])


def cmd_issue(args) -> int:
    action = args.action
    if action == "configure":
        cfg = issues.load_config()
        if args.repository:
            o, n = storage.parse_full_name(args.repository)
            cfg["repository"] = f"{o}/{n}"
        for key in ("template_path", "template_ref", "title", "milestone"):
            val = getattr(args, key)
            if val is not None:
                cfg[key] = val or None
        if args.labels is not None:
            cfg["extra_labels"] = issues._as_list(args.labels)
        if args.assignees is not None:
            cfg["default_assignees"] = issues._as_list(args.assignees)
        if args.enable:
            cfg["enabled"] = True
        if args.disable:
            cfg["enabled"] = False
        issues.save_config(cfg)
        args.action = "config"
        return cmd_issue(args)
    if action == "config":
        cfg = issues.load_config()
        _print(json.dumps(cfg, ensure_ascii=False, indent=2))
        problems = issues.config_problems(cfg)
        _print("\nStatus: " + ("klar att använda." if not problems else
                               "inte klar:\n  - " + "\n  - ".join(problems)))
        return 0 if not problems else 3
    if action == "template":
        t = _load_template(args.file)
        out = {k: v for k, v in t.items() if k not in ("body",)}
        out["questions"] = issues.questions(t)
        _print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    if action == "draft":
        cfg, _, _ = issues.require_config()
        t = _load_template(args.template_file)
        answers = _read_json_arg(args.answers, "Svars") or {}
        if not isinstance(answers, dict):
            raise MonitorError("Svarsfilen måste vara ett JSON-objekt (fält-id eller label -> svar).")
        meta = _read_json_arg(args.repo_meta, "Repo-meta")
        draft = issues.build_draft(cfg, t, answers, meta, args.assignees)
        if draft["status"] == "draft":
            issues.save_draft(draft)
        _print(issues.render_preview(draft, t))
        return 0 if draft["status"] == "draft" else 3
    if action == "payload":
        _, d = issues.find_draft(args.file)
        if d.get("status") != "draft":
            raise MonitorError(f"Utkastet har status '{d.get('status')}' och kan inte skickas.")
        _print(json.dumps(d["payload"], ensure_ascii=False, indent=2))
        return 0
    if action == "list":
        d = issues.drafts_dir()
        files = sorted(d.glob("*.json")) if d.exists() else []
        if not files:
            _print("Inga utkast.")
        for f in files:
            x = storage.read_json(f, {})
            _print(f"- {x.get('id')} [{x.get('status')}] {x.get('payload', {}).get('title')}"
                   + (f" → {x['issue_url']}" if x.get("issue_url") else ""))
        return 0
    if action == "record":
        path, d = issues.find_draft(args.file)
        if not args.url:
            raise MonitorError("Ange --url till den skapade issuen.")
        d["status"] = "created"
        d["issue_url"] = args.url
        d.setdefault("submitted_at", to_iso(now_utc()))
        storage.write_json(path, d)
        _print(f"Utkast {d['id']} markerat som skapat: {args.url}")
        return 0
    raise MonitorError(f"Okänd issue-åtgärd: {action}")


def cmd_discover(args) -> int:
    if args.action in ("config", "configure"):
        cfg = discovery.load_config()
        if args.action == "configure":
            if args.owner:
                cfg["owner"] = args.owner
            if args.pattern:
                import re as _re
                try:
                    if "username" not in _re.compile(args.pattern).groupindex:
                        raise MonitorError("Mönstret måste innehålla gruppen (?P<username>...).")
                except _re.error as exc:
                    raise MonitorError(f"Ogiltigt mönster: {exc}") from exc
                cfg["repo_name_pattern"] = args.pattern
            if args.name_template:
                if "{username}" not in args.name_template:
                    raise MonitorError("Namnmallen måste innehålla {username}.")
                cfg["repo_name_template"] = args.name_template
            if args.issues_repository is not None:
                cfg["issues_repository"] = args.issues_repository or None
            if args.labels is not None:
                cfg["issue_labels"] = issues._as_list(args.labels)
            if args.name_field:
                cfg["issue_fields"]["name"] = issues._as_list(args.name_field)
            if args.username_field:
                cfg["issue_fields"]["github_username"] = issues._as_list(args.username_field)
            discovery.save_config(cfg)
        _print(json.dumps(cfg, ensure_ascii=False, indent=2))
        _print(f"\nIssues läses från: {discovery.issues_repository(cfg) or '(inget repository konfigurerat)'}")
        return 0
    if args.action == "sync":
        cfg = discovery.load_config()
        issues_raw = _read_json_arg(args.issues, "Issue")
        repos_raw = _read_json_arg(args.repos, "Repository")
        if issues_raw is None and repos_raw is None:
            raise MonitorError("Ange --issues och/eller --repos.")
        registry = storage.load_registry()
        result = discovery.sync(registry, issues_raw, repos_raw, cfg)
        storage.save_registry(registry)
        _print(json.dumps(result, ensure_ascii=False, indent=2) if args.format == "json"
               else discovery.render_sync(result))
        return 0
    raise MonitorError(f"Okänd åtgärd: {args.action}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="repo_monitor", description="GitHub Repository Monitor")
    sub = p.add_subparsers(dest="command", required=True)

    a = sub.add_parser("analyze", help="Analysera en snapshot av ett repository")
    a.add_argument("snapshot")
    a.add_argument("--view", choices=VIEWS, default="report")
    a.add_argument("--format", choices=("md", "json"), default="md")
    g = a.add_mutually_exclusive_group()
    g.add_argument("--save", dest="save", action="store_true", default=None,
                   help="Spara som kontroll (historik)")
    g.add_argument("--no-save", dest="save", action="store_false")
    a.add_argument("--now", help=argparse.SUPPRESS)
    a.set_defaults(func=cmd_analyze)

    o = sub.add_parser("overview", help="Översikt över flera repositories")
    o.add_argument("snapshots", nargs="*")
    o.add_argument("--format", choices=("md", "json"), default="md")
    g = o.add_mutually_exclusive_group()
    g.add_argument("--save", dest="save", action="store_true", default=None)
    g.add_argument("--no-save", dest="save", action="store_false")
    o.add_argument("--now", help=argparse.SUPPRESS)
    o.set_defaults(func=cmd_overview)

    t = sub.add_parser("template", help="Skriv ut en tom snapshot-mall")
    t.add_argument("repo")
    t.set_defaults(func=cmd_template)

    r = sub.add_parser("registry", help="Hantera registret")
    r.add_argument("action", choices=("list", "show", "find", "add", "remove", "set-automation"))
    r.add_argument("repo", nargs="?", help="ägare/namn (för set-automation: kommaseparerade konton)")
    r.add_argument("--project-name")
    r.add_argument("--url")
    r.add_argument("--created-at")
    r.add_argument("--invited", help="Kommaseparerade GitHub-användarnamn")
    r.add_argument("--issue", type=int, help="Nummer på inbjudnings-issue")
    r.add_argument("--source", help="t.ex. automation, manual, discovered")
    r.add_argument("--format", choices=("text", "json"), default="text")
    r.set_defaults(func=cmd_registry)

    i = sub.add_parser("issue", help="Skapa issue från den konfigurerade templaten")
    i.add_argument("action", choices=("config", "configure", "template", "draft", "payload", "list", "record"))
    i.add_argument("file", nargs="?", help="template-fil (template) eller utkast-id (payload/record)")
    i.add_argument("--repository")
    i.add_argument("--template-path")
    i.add_argument("--template-ref")
    i.add_argument("--title")
    i.add_argument("--labels", help="Extra labels (kommaseparerade)")
    i.add_argument("--assignees", help="Assignees (kommaseparerade)")
    i.add_argument("--milestone")
    i.add_argument("--enable", action="store_true")
    i.add_argument("--disable", action="store_true")
    i.add_argument("--template-file", help="Lokalt sparad kopia av templaten")
    i.add_argument("--answers", help="JSON-fil med svar")
    i.add_argument("--repo-meta", help="JSON-fil med verifierade labels/assignees/milestones")
    i.add_argument("--url")
    i.set_defaults(func=cmd_issue)

    d = sub.add_parser("discover", help="Hitta challenge-repositories och personer")
    d.add_argument("action", choices=("config", "configure", "sync"))
    d.add_argument("--owner")
    d.add_argument("--pattern", help="Regex för repo-namn med gruppen (?P<username>...)")
    d.add_argument("--name-template", help="t.ex. ivy-engineering-challenge-{username}")
    d.add_argument("--issues-repository", help="Repo där beställnings-issues finns (standard: issue-config)")
    d.add_argument("--labels", help="Bara issues med någon av dessa labels")
    d.add_argument("--name-field", help="Template-fält (label) med personens namn, kommaseparerade alternativ")
    d.add_argument("--username-field", help="Template-fält (label) med GitHub-användarnamn")
    d.add_argument("--issues", help="JSON-fil med svaret från list_issues")
    d.add_argument("--repos", help="JSON-fil med svaret från search_repositories")
    d.add_argument("--format", choices=("md", "json"), default="md")
    d.set_defaults(func=cmd_discover)

    s = sub.add_parser("state", help="Visa sparad historik")
    s.add_argument("action", choices=("show",))
    s.add_argument("repo")
    s.set_defaults(func=cmd_state)
    return p


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "registry" and args.action not in ("list", "set-automation") and not args.repo:
        parser.error("ange ett repository (ägare/namn)")
    try:
        return args.func(args)
    except MonitorError as exc:
        sys.stderr.write(f"Fel: {exc}\n")
        return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
