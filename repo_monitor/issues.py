"""Skapa GitHub-issues från en fast, konfigurerad template.

Scope: ETT konfigurerat repository och EN konfigurerad template. Issuen används
för att trigga en GitHub Action, så innehållet måste följa templaten exakt.

Flöde:
  1. Agenten hämtar templaten via GitHub MCP och sparar den lokalt.
  2. `issue draft` tolkar templaten, validerar svaren och skapar ett utkast.
  3. Användaren godkänner utkastet uttryckligen.
  4. Agenten anropar MCP:s issue_write (method=create) med exakt utkastets innehåll.
  5. En PreToolUse-hook (guard) stoppar allt som inte matchar konfiguration + utkast,
     och tvingar fram en extra bekräftelse i Claude Code.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from . import miniyaml, storage
from .storage import MonitorError, read_json, write_json
from .timeutil import now_utc, to_iso

NO_RESPONSE = "_No response_"
PLACEHOLDER = "ÄGARE/REPO"


# --------------------------------------------------------------------------
# Konfiguration
# --------------------------------------------------------------------------

def config_path() -> Path:
    return storage.home() / "issue-config.json"


def drafts_dir() -> Path:
    return storage.home() / "issue-drafts"


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
                requested_assignees=None) -> dict:
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

    ready = not missing and not errors
    return {
        "id": None,
        "status": "draft" if ready else "incomplete",
        "created_at": to_iso(now_utc()),
        "repository": f"{owner}/{name}",
        "template_path": template["path"],
        "template_name": template.get("name"),
        "template_sha256": template["sha256"],
        "payload": payload,
        "missing": missing,
        "errors": errors,
        "warnings": warnings,
        "answers": answers,
    }


def save_draft(draft: dict) -> Path:
    stamp = now_utc().strftime("%Y%m%dT%H%M%SZ")
    digest = payload_digest(draft["payload"])[:8]
    draft["id"] = f"{stamp}-{digest}"
    path = drafts_dir() / f"{draft['id']}.json"
    write_json(path, draft)
    return path


def render_preview(draft: dict, template: dict) -> str:
    p = draft["payload"]
    lines = ["## Ny GitHub Issue (utkast)", "",
             f"- **Repository:** {draft['repository']}",
             f"- **Template:** {template.get('name') or draft['template_path']} (`{draft['template_path']}`)",
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
    if draft["status"] == "draft":
        lines += ["", f"Utkast-id: `{draft['id']}`", "",
                  "**Vill du att jag skapar denna issue?** (svara ja för att skapa den)"]
    else:
        lines += ["", "*Utkastet är inte klart och kan inte skapas ännu.*"]
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# Spärr (används av .claude/hooks/issue_guard.py)
# --------------------------------------------------------------------------

def _norm_payload(p: dict) -> dict:
    return {
        "method": str(p.get("method") or ""),
        "owner": str(p.get("owner") or "").lower(),
        "repo": str(p.get("repo") or "").lower(),
        "title": (p.get("title") or "").strip(),
        "body": (p.get("body") or "").replace("\r\n", "\n").strip(),
        "labels": sorted(p.get("labels") or []),
        "assignees": sorted(a.lower() for a in (p.get("assignees") or [])),
        "milestone": int(p["milestone"]) if p.get("milestone") not in (None, "") else None,
    }


def payload_digest(p: dict) -> str:
    return hashlib.sha256(json.dumps(_norm_payload(p), sort_keys=True).encode("utf-8")).hexdigest()


def _drafts():
    d = drafts_dir()
    if not d.exists():
        return []
    out = []
    for f in sorted(d.glob("*.json")):
        data = read_json(f, None)
        if isinstance(data, dict):
            out.append((f, data))
    return out


def check_issue_write(tool_input: dict) -> tuple[str, str]:
    """Returnerar ('deny'|'ask', motivering)."""
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
    digest = payload_digest(tool_input)
    created_match = None
    for path, d in _drafts():
        if payload_digest(d.get("payload") or {}) != digest:
            continue
        if d.get("status") == "draft":
            return "ask", (f"Skapa issue i {owner}/{name}: ”{tool_input.get('title')}” "
                           f"(utkast {d.get('id')}). Godkänn bara om användaren har sagt ja till utkastet.")
        if d.get("status") == "created":
            created_match = d
    if created_match:
        return "deny", (f"Denna issue är redan skapad ({created_match.get('issue_url') or 'se utkast ' + str(created_match.get('id'))}). "
                        "Skapa ett nytt utkast om en till issue verkligen ska skapas.")
    return "deny", ("Innehållet matchar inget godkänt utkast. Skapa utkastet med "
                    "`python3 -m repo_monitor issue draft`, visa det för användaren och använd "
                    "exakt payload från `python3 -m repo_monitor issue payload <id>`.")


_ISSUE_URL = re.compile(r"https://github\.com/[^/\s\"]+/[^/\s\"]+/issues/\d+")


def record_created(tool_input: dict, tool_response) -> dict | None:
    """Markerar matchande utkast som skapat. Returnerar utkastet eller None."""
    digest = payload_digest(tool_input)
    text = tool_response if isinstance(tool_response, str) else json.dumps(tool_response, ensure_ascii=False)
    m = _ISSUE_URL.search(text or "")
    for path, d in _drafts():
        if d.get("status") == "draft" and payload_digest(d.get("payload") or {}) == digest:
            d["status"] = "created"
            d["submitted_at"] = to_iso(now_utc())
            if m:
                d["issue_url"] = m.group(0)
                d["issue_number"] = int(m.group(0).rsplit("/", 1)[1])
            after_created(d)
            write_json(path, d)
            return d
    return None


def after_created(draft: dict) -> None:
    """Registrerar kandidaten i monitorn så att man direkt kan fråga om repot."""
    from . import discovery  # undvik cirkulär import
    try:
        registry = storage.load_registry()
        entry = discovery.register_invitation(registry, draft)
        if entry is not None:
            storage.save_registry(registry)
            draft["registered_repository"] = f"{entry['owner']}/{entry['name']}"
        else:
            draft["registered_repository"] = None
            draft.setdefault("warnings", []).append(
                "Kandidaten kunde inte registreras i monitorn: inget GitHub-användarnamn hittades i "
                "issuen. Kontrollera issue_fields i repo-monitor/discovery.json.")
    except Exception as exc:  # registreringen får aldrig stoppa själva issuen
        draft["registered_repository"] = None
        draft.setdefault("warnings", []).append(f"Registrering i monitorn misslyckades: {exc}")


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


def find_draft(draft_id: str) -> tuple[Path, dict]:
    path = drafts_dir() / f"{draft_id}.json"
    if not path.exists():
        cands = [p for p in drafts_dir().glob(f"*{draft_id}*.json")] if drafts_dir().exists() else []
        if len(cands) != 1:
            raise MonitorError(f"Hittar inget utkast med id {draft_id}.")
        path = cands[0]
    return path, read_json(path)
