"""Inställningar och gemensamma hjälpfunktioner.

Repository Monitor sparar ingen data lokalt: all information hämtas från GitHub via
MCP varje gång. Det enda som ligger på disk är inställningar (konfiguration) i
<projektrot>/repo-monitor. Katalogen kan pekas om med REPO_MONITOR_HOME (används av testerna).
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class MonitorError(Exception):
    """Fel som ska visas för användaren som ett begripligt meddelande."""


def home() -> Path:
    return Path(os.environ.get("REPO_MONITOR_HOME") or PROJECT_ROOT / "repo-monitor")


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


def read_json(path: Path, default=None):
    if not path.exists():
        return default
    try:
        with path.open(encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as exc:
        raise MonitorError(
            f"Filen {path} är skadad och kunde inte läsas (rad {exc.lineno}). "
            "Återställ den med git eller skapa om inställningarna."
        ) from exc


def write_json(path: Path, data) -> None:
    """Atomisk skrivning (används bara för inställningar)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def read_input(path: str | None, what: str = "Indata") -> str:
    """Läser text från en fil, eller från stdin om path är None eller '-'."""
    if path in (None, "-"):
        text = sys.stdin.read()
        if not text.strip():
            raise MonitorError(f"{what} saknas: skicka den på stdin eller ange en fil.")
        return text
    p = Path(path)
    if not p.exists():
        raise MonitorError(f"{what}-filen {path} finns inte.")
    return p.read_text(encoding="utf-8")


def read_json_input(path: str | None, what: str = "Indata"):
    text = read_input(path, what)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise MonitorError(
            f"{what} är inte giltig JSON (rad {exc.lineno}, kolumn {exc.colno}): {exc.msg}"
        ) from exc
