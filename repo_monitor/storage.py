"""Lagring av register, historik (state) och rapporter som JSON/Markdown-filer.

Allt ligger under en datakatalog (standard: <projektrot>/repo-monitor).
Den kan pekas om med miljövariabeln REPO_MONITOR_HOME (används av testerna).
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path

from .timeutil import now_utc, to_iso

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REGISTRY_VERSION = 1


class MonitorError(Exception):
    """Fel som ska visas för användaren som ett begripligt meddelande."""


def home() -> Path:
    return Path(os.environ.get("REPO_MONITOR_HOME") or PROJECT_ROOT / "repo-monitor")


def registry_path() -> Path:
    return home() / "registry.json"


def state_dir() -> Path:
    return home() / "state"


def reports_dir() -> Path:
    return home() / "reports"


# --------------------------------------------------------------------------
# Hjälpfunktioner
# --------------------------------------------------------------------------

_SLUG_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def parse_full_name(text: str) -> tuple[str, str]:
    """'owner/repo' eller en GitHub-URL -> ('owner', 'repo')."""
    if not text:
        raise MonitorError("Inget repository angavs. Använd formatet ägare/namn.")
    t = text.strip()
    t = re.sub(r"^https?://(www\.)?github\.com/", "", t)
    t = t.rstrip("/")
    if t.endswith(".git"):
        t = t[:-4]
    parts = t.split("/")
    if len(parts) >= 2:
        t = "/".join(parts[:2])
    if not _SLUG_RE.match(t):
        raise MonitorError(
            f"'{text}' ser inte ut som ett repository. Använd formatet ägare/namn, "
            "t.ex. min-organisation/mitt-projekt."
        )
    owner, name = t.split("/")
    return owner, name


def repo_key(owner: str, name: str) -> str:
    return f"{owner}/{name}".lower()


def _file_stem(owner: str, name: str) -> str:
    return f"{owner}__{name}".lower()


def read_json(path: Path, default=None):
    if not path.exists():
        return default
    try:
        with path.open(encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as exc:
        raise MonitorError(
            f"Filen {path} är skadad och kunde inte läsas (rad {exc.lineno}). "
            "Rätta eller ta bort filen och försök igen."
        ) from exc


def write_json(path: Path, data) -> None:
    """Atomisk skrivning: skriv till temporär fil och byt namn."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2, sort_keys=False)
            fh.write("\n")
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


# --------------------------------------------------------------------------
# Register
# --------------------------------------------------------------------------

def empty_registry() -> dict:
    return {
        "version": REGISTRY_VERSION,
        "description": (
            "Register över repositories som skapats av det automatiserade repo-flödet "
            "och som Repository Monitor ska följa."
        ),
        "automation_accounts": [],
        "repositories": [],
    }


def load_registry() -> dict:
    data = read_json(registry_path(), None)
    if data is None:
        return empty_registry()
    data.setdefault("automation_accounts", [])
    data.setdefault("repositories", [])
    return data


def save_registry(registry: dict) -> None:
    write_json(registry_path(), registry)


def find_entry(registry: dict, owner: str, name: str) -> dict | None:
    key = repo_key(owner, name)
    for entry in registry["repositories"]:
        if repo_key(entry["owner"], entry["name"]) == key:
            return entry
    return None


def upsert_entry(registry: dict, owner: str, name: str, **fields) -> tuple[dict, bool]:
    """Lägger till eller uppdaterar en post. Returnerar (post, skapad)."""
    entry = find_entry(registry, owner, name)
    created = entry is None
    if created:
        entry = {
            "owner": owner,
            "name": name,
            "url": f"https://github.com/{owner}/{name}",
            "project_name": name,
            "created_at": None,
            "invited_contributors": [],
            "contributors": [],
            "last_activity": None,
            "source": "manual",
            "registered_at": to_iso(now_utc()),
        }
        registry["repositories"].append(entry)
    for key, value in fields.items():
        if value is None:
            continue
        if key == "invited_contributors":
            merged = list(dict.fromkeys([*entry.get(key, []), *value]))
            entry[key] = merged
        else:
            entry[key] = value
    return entry, created


def remove_entry(registry: dict, owner: str, name: str) -> bool:
    key = repo_key(owner, name)
    before = len(registry["repositories"])
    registry["repositories"] = [
        e for e in registry["repositories"] if repo_key(e["owner"], e["name"]) != key
    ]
    return len(registry["repositories"]) != before


# --------------------------------------------------------------------------
# Historik (state) per repository
# --------------------------------------------------------------------------

def state_path(owner: str, name: str) -> Path:
    return state_dir() / f"{_file_stem(owner, name)}.json"


def load_state(owner: str, name: str) -> dict | None:
    return read_json(state_path(owner, name), None)


def save_state(owner: str, name: str, state: dict) -> None:
    write_json(state_path(owner, name), state)


def save_report(owner: str, name: str, markdown: str, when) -> Path:
    """Sparar rapporten både som latest.md och med tidsstämpel."""
    folder = reports_dir() / _file_stem(owner, name)
    folder.mkdir(parents=True, exist_ok=True)
    stamp = when.strftime("%Y%m%dT%H%M%SZ")
    dated = folder / f"{stamp}.md"
    dated.write_text(markdown, encoding="utf-8")
    (folder / "latest.md").write_text(markdown, encoding="utf-8")
    return dated
