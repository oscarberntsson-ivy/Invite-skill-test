"""Skapa GitHub-issues från en fast, konfigurerad template (inbjudan av kandidat).

Scope: ETT konfigurerat repository och EN konfigurerad template. Issuen används
för att trigga en GitHub Action, så innehållet måste följa templaten exakt.
Inget sparas lokalt.

Flöde:
  1. Agenten hämtar templaten via GitHub MCP och skickar den hit (stdin).
  2. `issue questions` visar templatens frågor; användaren svarar.
  3. `issue draft` validerar svaren, kontrollerar dubbla inbjudningar mot befintliga
     issues och bygger exakt det som ska skickas.
  4. Användaren godkänner utkastet uttryckligen.
  5. Agenten anropar MCP:s issue_write (method=create). En PreToolUse-hook nekar allt
     som inte är en ny issue i det konfigurerade repositoryt, och Claude Code visar
     anropet och frågar användaren en gång till.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from . import miniyaml, storage
from .storage import MonitorError, read_json, write_json

NO_RESPONSE = "_No response_"
PLACEHOLDER = "ÄGARE/REPO"


# --------------------------------------------------------------------------
# Konfiguration
# --------------------------------------------------------------------------

def config_path() -> Path:
    return storage.home() / "issue-config.json"


def default_config() -> dict:
    return {
        "enabled": False,
        "repository": PLACEHOLDER,
        "template_path": ".github/ISSUE_TEMPLATE/MALL.yml",
        "template_ref": None,
        "title": None,
        "extra_labels": [],
        "default_assignees": [],
        "milestone": None,
        "purpose": "Issue som triggar en GitHub Action.",
    }


def load_config() -> dict:
    cfg = read_json(config_path(), None)
    base = default_config()
    if cfg:
        base.update(cfg)
    return base


def save_config(cfg: dict) -> None:
    write_json(config_path(), cfg)


def config_problems(cfg: dict) -> list[str]:
    problems = []
    repo = cfg.get("repository") or ""
    if not repo or repo == PLACEHOLDER:
        problems.append("Inget repository är konfigurerat (fältet 'repository').")
    else:
        try:
            storage.parse_full_name(repo)
        except MonitorError as exc:
            problems.append(str(exc))
    tp = cfg.get("template_path") or ""
    if not tp or "MALL" in tp:
        problems.append("Ingen template är konfigurerad (fältet 'template_path').")
    elif not re.search(r"\.(ya?ml|md)$", tp, re.I):
        problems.append("template_path måste peka på en .yml-, .yaml- eller .md-fil.")
    if not cfg.get("enabled"):
        problems.append("Funktionen är avstängd ('enabled': false).")
    return problems


def require_config() -> tuple[dict, str, str]:
    cfg = load_config()
    problems = config_problems(cfg)
    if problems:
        raise MonitorError(
            "Issue-funktionen är inte konfigurerad:\n  - " + "\n  - ".join(problems) +
            "\nKonfigurera med: python3 -m repo_monitor issue configure "
            "--repository ägare/repo --template-path .github/ISSUE_TEMPLATE/fil.yml --enable"
        )
    owner, name = storage.parse_full_name(cfg["repository"])
    return cfg, owner, name


# --------------------------------------------------------------------------
# Template-tolkning
# --------------------------------------------------------------------------

def _as_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [v.strip() for v in value.split(",") if v.strip()]
    return [str(v).strip() for v in value if str(v).strip()]


def parse_template(text: str, path: str) -> dict:
    if re.search(r"\.ya?ml$", path, re.I):
        return _parse_form(text, path)
    if path.lower().endswith(".md"):
        return _parse_markdown(text, path)
    raise MonitorError(f"Okänd template-typ: {path}")


def _parse_form(text: str, path: str) -> dict:
    try:
        data = miniyaml.load(text)
    except miniyaml.YamlError as exc:
        raise MonitorError(f"Templaten {path} kunde inte tolkas som YAML: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("body"), list):
        raise MonitorError(f"Templaten {path} är inte ett giltigt issue form (saknar 'body').")
    fields = []
    for idx, el in enumerate(data["body"]):
        if not isinstance(el, dict) or not el.get("type"):
            raise MonitorError(f"Element {idx + 1} i {path} saknar 'type'.")
        attrs = el.get("attributes") or {}
        val = el.get("validations") or {}
        f = {
            "type": el["type"],
            "id": el.get("id"),
            "label": attrs.get("label"),
            "description": attrs.get("description"),
            "placeholder": attrs.get("placeholder"),
            "value": attrs.get("value"),
            "render": attrs.get("render"),
            "multiple": bool(attrs.get("multiple")),
            "default": attrs.get("default"),
            "required": bool(val.get("required")),
            "options": [],
        }
        if el["type"] == "dropdown":
            f["options"] = [str(o) for o in attrs.get("options") or []]
        elif el["type"] == "checkboxes":
            f["options"] = [
                {"label": str(o.get("label")), "required": bool(o.get("required"))}
                if isinstance(o, dict) else {"label": str(o), "required": False}
                for o in attrs.get("options") or []
            ]
        if el["type"] != "markdown" and not f["label"]:
            raise MonitorError(f"Fält {idx + 1} ({el['type']}) i {path} saknar label.")
        fields.append(f)
    return {
        "kind": "form",
        "path": path,
        "name": data.get("name"),
        "description": data.get("description"),
        "title": data.get("title"),
        "labels": _as_list(data.get("labels")),
        "assignees": _as_list(data.get("assignees")),
        "projects": _as_list(data.get("projects")),
        "type": data.get("type"),
        "fields": fields,
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }


_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")


def _parse_markdown(text: str, path: str) -> dict:
    meta, body = {}, text
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, re.S)
    if m:
        try:
            meta = miniyaml.load(m.group(1)) or {}
        except miniyaml.YamlError as exc:
            raise MonitorError(f"Front matter i {path} kunde inte tolkas: {exc}") from exc
        body = m.group(2)
    headings = [mm.group(2) for line in body.splitlines() if (mm := _HEADING.match(line))]
    return {
        "kind": "markdown",
        "path": path,
        "name": meta.get("name"),
        "description": meta.get("about"),
        "title": meta.get("title") or None,
        "labels": _as_list(meta.get("labels")),
        "assignees": _as_list(meta.get("assignees")),
        "projects": [],
        "type": meta.get("type"),
        "body": body,
        "headings": headings,
        "fields": [],
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }


def questions(template: dict) -> list[dict]:
    """Det användaren behöver svara på (för att agenten ska kunna fråga)."""
    out = []
    if template["kind"] == "form":
        for f in template["fields"]:
            if f["type"] == "markdown":
                continue
            out.append({
                "key": f["id"] or f["label"],
                "label": f["label"],
                "type": f["type"],
                "required": f["required"] or any(o.get("required") for o in f["options"]
                                                 if isinstance(o, dict)),
                "description": f.get("description"),
                "placeholder": f.get("placeholder"),
                "options": [o["label"] if isinstance(o, dict) else o for o in f["options"]],
                "multiple": f["multiple"],
            })
    else:
        for h in template["headings"]:
            out.append({"key": h, "label": h, "type": "section", "required": False,
                        "description": None, "placeholder": None, "options": [], "multiple": False})
    return out


# --------------------------------------------------------------------------
# Utkast
# --------------------------------------------------------------------------

def _answer(answers: dict, f: dict):
    for k in (f.get("id"), f.get("label")):
        if k and k in answers:
            return answers[k]
    return None


def _blank(v) -> bool:
    return v is None or (isinstance(v, str) and not v.strip()) or (isinstance(v, list) and not v)


def _render_form(template: dict, answers: dict, missing: list, errors: list) -> str:
    sections = []
    for f in template["fields"]:
        if f["type"] == "markdown":
            continue
        a = _answer(answers, f)
        label = f["label"]
        if f["type"] in ("input", "textarea"):
            if _blank(a) and not _blank(f.get("value")):
                a = f["value"]  # GitHub skickar det förifyllda värdet om inget ändras
            if _blank(a):
                if f["required"]:
                    missing.append(label)
                value = NO_RESPONSE
            else:
                value = str(a).strip()
                if f.get("render"):
                    value = f"```{f['render']}\n{value}\n```"
        elif f["type"] == "dropdown":
            chosen = a if isinstance(a, list) else ([] if _blank(a) else [a])
            if _blank(chosen) and f.get("default") is not None and not f["required"]:
                try:
                    chosen = [f["options"][int(f["default"])]]
                except (ValueError, IndexError):
                    chosen = []
            chosen = [str(c) for c in chosen]
            bad = [c for c in chosen if c not in f["options"]]
            if bad:
                errors.append(f"”{label}”: {', '.join(bad)} är inte ett giltigt val. "
                              f"Välj bland: {', '.join(f['options'])}.")
            if len(chosen) > 1 and not f["multiple"]:
                errors.append(f"”{label}”: bara ett val är tillåtet.")
            if not chosen and f["required"]:
                missing.append(label)
            value = ", ".join(chosen) if chosen else NO_RESPONSE
        elif f["type"] == "checkboxes":
            labels = [o["label"] for o in f["options"]]
            if a is True:
                checked = set(labels)
            else:
                checked = {str(x) for x in (a or [])} if not isinstance(a, str) else {a}
            bad = checked - set(labels)
            if bad:
                errors.append(f"”{label}”: okänt alternativ {', '.join(sorted(bad))}.")
            for o in f["options"]:
                if o["required"] and o["label"] not in checked:
                    missing.append(f"{label}: {o['label']}")
            value = "\n".join(f"- [{'X' if o['label'] in checked else ' '}] {o['label']}"
                              for o in f["options"])
        else:
            errors.append(f"Fälttypen '{f['type']}' stöds inte.")
            continue
        sections.append(f"### {label}\n\n{value}")
    known = {k for f in template["fields"] for k in (f.get("id"), f.get("label")) if k}
    extra = [k for k in answers if k not in known and k != "title"]
    if extra:
        errors.append("Svar som inte motsvarar något fält i templaten: " + ", ".join(extra) +
                      ". Templaten får inte utökas med egna fält.")
    return "\n\n".join(sections)


def _render_markdown(template: dict, answers: dict, missing: list, errors: list) -> str:
    if "body" in answers:
        body = str(answers["body"])
        pos = 0
        for h in template["headings"]:
            idx = body.find(h, pos)
            if idx < 0:
                errors.append(f"Rubriken ”{h}” från templaten saknas eller är i fel ordning. "
                              "Templatens struktur måste behållas.")
                continue
            pos = idx + len(h)
        return body.strip()
    out, current = [], None
    sections = {k: v for k, v in answers.items() if k != "title"}
    unknown = [k for k in sections if k not in template["headings"]]
    if unknown:
        errors.append("Svar till rubriker som inte finns i templaten: " + ", ".join(unknown))
    skipping = False
    for line in template["body"].splitlines():
        m = _HEADING.match(line)
        if m:
            current = m.group(2)
            out.append(line)
            if current in sections and not _blank(sections[current]):
                out += ["", str(sections[current]).strip(), ""]
                skipping = True
            else:
                skipping = False
            continue
        if not skipping:
            out.append(line)
    return "\n".join(out).strip()


def _title(cfg: dict, template: dict, answers: dict, missing: list) -> str:
    if cfg.get("title"):
        return cfg["title"]
    prefix = template.get("title") or ""
    given = str(answers.get("title") or "").strip()
    if not given:
        if not prefix.strip() or prefix.rstrip().endswith(":"):
            missing.append("Titel")
        return prefix.strip()
    if prefix and not given.startswith(prefix.strip()):
        return prefix + given if prefix.endswith(" ") else f"{prefix} {given}".strip()
    return given


def build_draft(cfg: dict, template: dict, answers: dict, repo_meta: dict | None,
                requested_assignees=None, existing_issues=None) -> dict:
    """Bygger utkastet. `existing_issues` (svaret från list_issues) används för att hitta
    dubbla inbjudningar. Inget sparas lokalt."""
    owner, name = storage.parse_full_name(cfg["repository"])
    missing, errors, warnings = [], [], []
    meta = repo_meta or {}

    if template["kind"] == "form":
        body = _render_form(template, answers, missing, errors)
    else:
        body = _render_markdown(template, answers, missing, errors)
    title = _title(cfg, template, answers, missing)

    # Labels: templatens labels + konfigurerade. Måste finnas i repot.
    labels = list(dict.fromkeys(template["labels"] + _as_list(cfg.get("extra_labels"))))
    existing = meta.get("labels_existing")
    missing_labels = set(meta.get("labels_missing") or [])
    if existing is None and not missing_labels:
        if labels:
            errors.append("Det är inte kontrollerat att labels finns i repot: " + ", ".join(labels) +
                          ". Kontrollera varje label med get_label och ange resultatet i repo-meta.")
    else:
        existing_l = {l.lower() for l in existing or []}
        for l in labels:
            if l in missing_labels or l.lower() not in existing_l:
                errors.append(f"Labeln ”{l}” finns inte i {owner}/{name}. GitHub Action kan bero på "
                              "den, så issuen skapas inte. Skapa labeln i repot eller ändra konfigurationen.")

    # Assignees: bara personer som kan tilldelas.
    assignees = list(dict.fromkeys(template["assignees"] + _as_list(cfg.get("default_assignees")) +
                                   _as_list(requested_assignees)))
    assignable = meta.get("assignable")
    if assignees:
        if assignable is None:
            warnings.append("Det gick inte att kontrollera vilka som kan tilldelas, så inga "
                            "assignees sätts: " + ", ".join(assignees) + ".")
            assignees = []
        else:
            ok = {a.lower() for a in assignable}
            dropped = [a for a in assignees if a.lower() not in ok]
            if dropped:
                warnings.append("Tas bort eftersom de inte kan tilldelas i repot: " + ", ".join(dropped) + ".")
            assignees = [a for a in assignees if a.lower() in ok]

    # Milestone: bara om den finns.
    milestone = None
    wanted = cfg.get("milestone")
    if wanted not in (None, ""):
        ms = meta.get("milestones")
        if ms is None:
            errors.append(f"Milestone ”{wanted}” är konfigurerad men kunde inte kontrolleras.")
        else:
            match = [m for m in ms if str(m.get("number")) == str(wanted)
                     or str(m.get("title", "")).lower() == str(wanted).lower()]
            if not match:
                errors.append(f"Milestone ”{wanted}” finns inte i {owner}/{name}.")
            else:
                milestone = int(match[0]["number"])

    payload = {"method": "create", "owner": owner, "repo": name, "title": title, "body": body}
    if labels:
        payload["labels"] = labels
    if assignees:
        payload["assignees"] = assignees
    if milestone is not None:
        payload["milestone"] = milestone

    # Dubbla inbjudningar: finns det redan en issue för samma GitHub-användarnamn?
    duplicate = None
    if existing_issues is not None:
        from . import discovery  # undvik cirkulär import
        dcfg = discovery.load_config()
        mine = discovery.person_from_issue({"body": body}, dcfg, None)
        if mine:
            for issue in discovery._issue_list(existing_issues) or []:
                other = discovery.person_from_issue(issue, dcfg, f"{owner}/{name}")
                if other and other["username"].lower() == mine["username"].lower():
                    duplicate = other
                    if (issue.get("state") or "").lower() in ("open", ""):
                        errors.append(f"Det finns redan en öppen inbjudan för {mine['username']}: "
                                      f"issue #{other['issue_number']}. Ingen ny issue skapas.")
                    else:
                        warnings.append(f"{mine['username']} har bjudits in tidigare (stängd issue "
                                        f"#{other['issue_number']}).")
                    break
    else:
        warnings.append("Det är inte kontrollerat om personen redan har bjudits in.")

    ready = not missing and not errors
    return {
        "status": "ready" if ready else "incomplete",
        "repository": f"{owner}/{name}",
        "template_path": template["path"],
        "template_name": template.get("name"),
        "payload": payload,
        "missing": missing,
        "errors": errors,
        "warnings": warnings,
        "duplicate_of": duplicate["issue_url"] if duplicate else None,
    }


def render_preview(draft: dict) -> str:
    p = draft["payload"]
    lines = ["## Ny GitHub Issue (utkast)", "",
             f"- **Repository:** {draft['repository']}",
             f"- **Template:** {draft.get('template_name') or draft['template_path']} (`{draft['template_path']}`)",
             f"- **Titel:** {p['title'] or '(saknas)'}",
             f"- **Labels:** {', '.join(p.get('labels') or []) or 'inga'}",
             f"- **Assignees:** {', '.join(p.get('assignees') or []) or 'inga'}"]
    if p.get("milestone") is not None:
        lines.append(f"- **Milestone:** {p['milestone']}")
    lines += ["", "**Beskrivning:**", "", "````markdown", p["body"], "````"]
    if draft["missing"]:
        lines += ["", "### Uppgifter som saknas", ""] + [f"- {m}" for m in draft["missing"]]
    if draft["errors"]:
        lines += ["", "### Problem som måste lösas", ""] + [f"- {e}" for e in draft["errors"]]
    if draft["warnings"]:
        lines += ["", "### Observera", ""] + [f"- {w}" for w in draft["warnings"]]
    if draft["status"] == "ready":
        lines += ["", "**Vill du att jag skapar denna issue?** (svara ja för att skapa den)"]
    else:
        lines += ["", "*Utkastet är inte klart och kan inte skapas ännu.*"]
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# Spärr (används av .claude/hooks/issue_guard.py)
# --------------------------------------------------------------------------

def check_issue_write(tool_input: dict) -> tuple[str, str]:
    """Returnerar ('deny'|'ask', motivering). 'ask' betyder att användaren alltid
    måste bekräfta i Claude Code – och då ser exakt vad som skickas."""
    method = tool_input.get("method")
    if method != "create":
        return "deny", ("Repository Monitor får bara skapa nya issues (method=create). "
                        "Befintliga issues ändras aldrig.")
    try:
        cfg, owner, name = require_config()
    except MonitorError as exc:
        return "deny", str(exc)
    if (str(tool_input.get("owner", "")).lower(), str(tool_input.get("repo", "")).lower()) != \
            (owner.lower(), name.lower()):
        return "deny", (f"Issues får bara skapas i det konfigurerade repositoryt {owner}/{name}, "
                        f"inte i {tool_input.get('owner')}/{tool_input.get('repo')}.")
    if not str(tool_input.get("title") or "").strip() or not str(tool_input.get("body") or "").strip():
        return "deny", "Issuen saknar titel eller beskrivning. Skapa utkastet med `issue draft` först."
    return "ask", (f"Skapa issue i {owner}/{name}: ”{tool_input.get('title')}”. "
                   "Godkänn bara om användaren har sagt ja till exakt detta utkast.")


def record_created(tool_input: dict, tool_response) -> None:
    """Inget sparas lokalt längre. Finns kvar för hookens PostToolUse-anrop."""
    return None


def render_questions(template: dict) -> str:
    """Templatens frågor som ett numrerat meddelande på svenska."""
    lines = [f"För att bjuda in en kandidat behöver jag följande uppgifter "
             f"(enligt templaten ”{template.get('name') or template['path']}”):", ""]
    n = 0
    for q in questions(template):
        n += 1
        req = "**obligatorisk**" if q["required"] else "valfri"
        line = f"{n}. **{q['label']}** ({req})"
        if q.get("description"):
            line += f" – {q['description']}"
        lines.append(line)
        if q["options"]:
            kind = "kryssa i" if q["type"] == "checkboxes" else ("välj en eller flera" if q["multiple"] else "välj en")
            lines.append(f"   - {kind}: " + " · ".join(f"`{o}`" for o in q["options"]))
        if q.get("placeholder"):
            lines.append(f"   - exempel: {q['placeholder']}")
    if template["kind"] == "form" and (not template.get("title") or str(template["title"]).rstrip().endswith(":")):
        n += 1
        lines.append(f"{n}. **Titel på issuen** (valfri – annars föreslår jag en utifrån svaren)")
    lines += ["", "Svara gärna på alla på en gång, t.ex. med en rad per nummer."]
    return "\n".join(lines) + "\n"
