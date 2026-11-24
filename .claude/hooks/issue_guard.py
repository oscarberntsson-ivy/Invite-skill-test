#!/usr/bin/env python3
"""Spärr för att skapa GitHub-issues via MCP (issue_write).

PreToolUse  ("pre"):  nekar allt som inte är method=create i det konfigurerade
                      repositoryt och exakt matchar ett sparat utkast. Om allt
                      stämmer returneras "ask" så att användaren alltid måste
                      bekräfta i Claude Code innan issuen skapas.
PostToolUse ("post"): markerar utkastet som skapat och sparar länken, så att
                      samma issue inte kan skapas två gånger.

Fel i själva spärren leder alltid till "deny" (fail closed).
"""

import json
import os
import sys
from pathlib import Path

ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path(__file__).resolve().parents[2])
sys.path.insert(0, str(ROOT))


def _out(decision: str, reason: str) -> None:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": reason,
        }
    }, ensure_ascii=False))


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "pre"
    try:
        event = json.load(sys.stdin)
    except Exception:
        if mode == "pre":
            _out("deny", "Spärren kunde inte läsa anropet och nekar därför.")
        return 0
    tool_input = event.get("tool_input") or {}
    try:
        from repo_monitor import issues
        if mode == "pre":
            decision, reason = issues.check_issue_write(tool_input)
            _out(decision, reason)
        else:
            issues.record_created(tool_input, event.get("tool_response"))
    except Exception as exc:  # fail closed
        if mode == "pre":
            _out("deny", f"Spärren kunde inte kontrollera anropet ({exc}) och nekar därför.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
