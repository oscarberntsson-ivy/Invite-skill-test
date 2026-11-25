"""Kommandoradsgränssnitt: python3 -m repo_monitor <kommando>.

Inget sparas lokalt. Data som agenten hämtat via GitHub MCP skickas in på stdin
(eller som fil) och svaret skrivs ut. Det enda på disk är inställningar.

Kommandon:
  analyze  [SNAPSHOT|-] --view V [--since DATUM]  Analysera ett repository
  overview [FIL|-]                                Översikt över flera repositories
  people   [FIL|-] [--query TEXT]                 Kandidater från inbjudnings-issues och repo-sökning
  discover config|configure                       Inställningar för namnstandard och template-fält
  issue    config|configure|template|questions|draft   Bjuda in kandidat via issue
  template ÄGARE/REPO                             Tom snapshot-mall
"""

from __future__ import annotations

import argparse
import json
import re
import sys

from . import analysis as A
from . import discovery, issues, render, storage
from .snapshot import normalize
from .storage import MonitorError, read_input, read_json_input
from .timeutil import now_utc, parse_iso, to_iso

VIEWS = ("status", "activity", "contributors", "report", "candidate")


def _print(text: str) -> None:
    sys.stdout.write(text if text.endswith("\n") else text + "\n")


def _now(args):
    return parse_iso(args.now) if getattr(args, "now", None) else now_utc()


def _since(args):
    if not getattr(args, "since", None):
        return None
    dt = parse_iso(args.since)
    if dt is None:
        raise MonitorError(f"Ogiltigt datum för --since: {args.since}. Använd t.ex. 2026-11-20.")
    return to_iso(dt)


def _analyze_raw(raw, now, since=None) -> dict:
    snapshot = normalize(raw)
    automation = discovery.load_config().get("automation_accounts") or []
    return A.analyze(snapshot, automation, now, since)


# --------------------------------------------------------------------------
# Monitorering
# --------------------------------------------------------------------------

def cmd_analyze(args) -> int:
    raw = read_json_input(args.snapshot, "Snapshot")
    result = _analyze_raw(raw, _now(args), _since(args))
    if args.format == "json":
        _print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        _print(render.render(result, args.view))
    return 0


def cmd_overview(args) -> int:
    raw = read_json_input(args.snapshots, "Snapshots")
    if isinstance(raw, dict):
        raw = raw.get("snapshots")
    if not isinstance(raw, list):
        raise MonitorError('Översikten behöver en JSON-lista med snapshots (eller {"snapshots": [...]}).')
    now = _now(args)
    analyses = [_analyze_raw(s, now) for s in raw]
    if args.format == "json":
        _print(json.dumps({"checked_at": to_iso(now), "projects": analyses}, ensure_ascii=False, indent=2))
    else:
        _print(render.render_overview(analyses, now))
    return 0


def cmd_people(args) -> int:
    raw = read_json_input(args.file, "Indata")
    if not isinstance(raw, dict) or ("issues" not in raw and "repos" not in raw):
        raise MonitorError('Indata ska vara {"issues": <svar från list_issues>, "repos": <svar från '
                           'search_repositories eller null>}.')
    result = discovery.people(raw.get("issues"), raw.get("repos"), discovery.load_config())
    hits = discovery.find(result["people"], args.query) if args.query else None
    if args.format == "json":
        rows = hits if hits is not None else result["people"]
        out = {**result, "people": [{**p, "snapshot_person": discovery.snapshot_person(p)} for p in rows]}
        _print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        _print(discovery.render_people(result, hits, args.query))
    return 0


def cmd_template(args) -> int:
    owner, name = storage.parse_full_name(args.repo)
    template = {
        "fetched_at": to_iso(now_utc()),
        "access": {"ok": True, "error": None},
        "person": None,
        "repo": {"owner": owner, "name": name, "html_url": f"https://github.com/{owner}/{name}",
                 "created_at": None, "pushed_at": None, "default_branch": "main"},
        "branches": [],
        "commits_by_branch": {"main": []},
        "pull_requests": [],
        "errors": [],
    }
    _print(json.dumps(template, ensure_ascii=False, indent=2))
    return 0


# --------------------------------------------------------------------------
# Inställningar för upptäckt
# --------------------------------------------------------------------------

def cmd_discover(args) -> int:
    cfg = discovery.load_config()
    if args.action == "configure":
        if args.owner:
            cfg["owner"] = args.owner
        if args.pattern:
            try:
                if "username" not in re.compile(args.pattern).groupindex:
                    raise MonitorError("Mönstret måste innehålla gruppen (?P<username>...).")
            except re.error as exc:
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
        if args.automation_accounts is not None:
            cfg["automation_accounts"] = issues._as_list(args.automation_accounts)
        discovery.save_config(cfg)
    _print(json.dumps(cfg, ensure_ascii=False, indent=2))
    _print(f"\nInbjudnings-issues läses från: {discovery.issues_repository(cfg) or '(inget repository konfigurerat)'}")
    return 0


# --------------------------------------------------------------------------
# Bjuda in kandidat (issue)
# --------------------------------------------------------------------------

def _template_from(text: str) -> dict:
    cfg, _, _ = issues.require_config()
    return issues.parse_template(text, cfg["template_path"])


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
        action = "config"
    if action == "config":
        cfg = issues.load_config()
        _print(json.dumps(cfg, ensure_ascii=False, indent=2))
        problems = issues.config_problems(cfg)
        _print("\nStatus: " + ("klar att använda." if not problems else
                               "inte klar:\n  - " + "\n  - ".join(problems)))
        return 0 if not problems else 3
    if action == "template":
        t = _template_from(read_input(args.file, "Template"))
        out = dict(t)
        out.pop("body", None)
        out["questions"] = issues.questions(t)
        _print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    if action == "questions":
        _print(issues.render_questions(_template_from(read_input(args.file, "Template"))))
        return 0
    if action == "draft":
        cfg, _, _ = issues.require_config()
        data = read_json_input(args.file, "Utkastdata")
        if not isinstance(data, dict) or not isinstance(data.get("template"), str):
            raise MonitorError('Utkastdata ska vara {"template": "<templatens text>", "answers": {...}, '
                               '"meta": {...}, "existing_issues": <svar från list_issues>}.')
        answers = data.get("answers") or {}
        if not isinstance(answers, dict):
            raise MonitorError("answers måste vara ett objekt (fält-id eller label -> svar).")
        t = issues.parse_template(data["template"], cfg["template_path"])
        draft = issues.build_draft(cfg, t, answers, data.get("meta"), data.get("assignees"),
                                   data.get("existing_issues"))
        if args.format == "json":
            _print(json.dumps(draft, ensure_ascii=False, indent=2))
        else:
            _print(issues.render_preview(draft))
            if draft["status"] == "ready":
                _print("Exakt det som ska skickas till issue_write:\n```json\n" +
                       json.dumps(draft["payload"], ensure_ascii=False, indent=2) + "\n```")
        return 0 if draft["status"] == "ready" else 3
    raise MonitorError(f"Okänd issue-åtgärd: {action}")


# --------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="repo_monitor", description="GitHub Repository Monitor")
    sub = p.add_subparsers(dest="command", required=True)

    a = sub.add_parser("analyze", help="Analysera en snapshot (fil eller stdin)")
    a.add_argument("snapshot", nargs="?", default="-")
    a.add_argument("--view", choices=VIEWS, default="report")
    a.add_argument("--since", help="Räkna commits från och med detta datum (t.ex. 2026-11-20)")
    a.add_argument("--format", choices=("md", "json"), default="md")
    a.add_argument("--now", help=argparse.SUPPRESS)
    a.set_defaults(func=cmd_analyze)

    o = sub.add_parser("overview", help="Översikt över flera snapshots (JSON-lista, fil eller stdin)")
    o.add_argument("snapshots", nargs="?", default="-")
    o.add_argument("--format", choices=("md", "json"), default="md")
    o.add_argument("--now", help=argparse.SUPPRESS)
    o.set_defaults(func=cmd_overview)

    pe = sub.add_parser("people", help="Kandidater från inbjudnings-issues och repo-sökning")
    pe.add_argument("file", nargs="?", default="-")
    pe.add_argument("--query", help="Sök på namn, GitHub-användarnamn eller repo")
    pe.add_argument("--format", choices=("md", "json"), default="md")
    pe.set_defaults(func=cmd_people)

    t = sub.add_parser("template", help="Skriv ut en tom snapshot-mall")
    t.add_argument("repo")
    t.set_defaults(func=cmd_template)

    d = sub.add_parser("discover", help="Inställningar för namnstandard och template-fält")
    d.add_argument("action", choices=("config", "configure"))
    d.add_argument("--owner")
    d.add_argument("--pattern", help="Regex för repo-namn med gruppen (?P<username>...)")
    d.add_argument("--name-template", help="t.ex. ivy-engineering-challenge-{username}")
    d.add_argument("--issues-repository", help="Repo där inbjudnings-issues finns (standard: issue-config)")
    d.add_argument("--labels", help="Bara issues med någon av dessa labels")
    d.add_argument("--name-field", help="Template-fältets label för personens namn")
    d.add_argument("--username-field", help="Template-fältets label för GitHub-användarnamn")
    d.add_argument("--automation-accounts", help="Konton vars commits inte räknas som bidrag")
    d.set_defaults(func=cmd_discover)

    i = sub.add_parser("issue", help="Bjud in kandidat via issue från den konfigurerade templaten")
    i.add_argument("action", choices=("config", "configure", "template", "questions", "draft"))
    i.add_argument("file", nargs="?", default="-", help="Indata (fil eller - för stdin)")
    i.add_argument("--repository")
    i.add_argument("--template-path")
    i.add_argument("--template-ref")
    i.add_argument("--title")
    i.add_argument("--labels", help="Extra labels (kommaseparerade)")
    i.add_argument("--assignees", help="Assignees (kommaseparerade)")
    i.add_argument("--milestone")
    i.add_argument("--enable", action="store_true")
    i.add_argument("--disable", action="store_true")
    i.add_argument("--format", choices=("md", "json"), default="md")
    i.set_defaults(func=cmd_issue)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except MonitorError as exc:
        sys.stderr.write(f"Fel: {exc}\n")
        return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
