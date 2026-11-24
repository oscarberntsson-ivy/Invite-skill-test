---
name: repo-monitor-activity
description: "/repo-monitor:activity – Visar senaste aktivitet i ett repository som en tidslinje: commits, push, pull requests och merges."
argument-hint: "ägare/repo"
disable-model-invocation: true
allowed-tools: mcp__github__get_me, mcp__github__search_repositories, mcp__github__list_commits, mcp__github__get_commit, mcp__github__list_branches, mcp__github__list_pull_requests, mcp__github__pull_request_read, Bash(python3 -m repo_monitor:*), Read, Write(repo-monitor/snapshots/**)
---

# /repo-monitor:activity

Visar senaste aktivitet i ett repository som en tidslinje: commits, push, pull requests och merges.

Läs och följ arbetsflödet i `.claude/skills/repo-monitor/SKILL.md` med **läge `activity`**.

Repository: `$ARGUMENTS`. Om det är tomt, kör `python3 -m repo_monitor registry list` – finns exakt ett registrerat projekt används det, annars fråga användaren vilket projekt som avses.

Kort sammanfattning av flödet:
1. Hämta data via GitHub MCP (endast läsverktyg) enligt steg 2 i huvudskillen.
2. Skriv snapshot till `repo-monitor/snapshots/ÄGARE__NAMN.json`.
3. Kör `python3 -m repo_monitor analyze <snapshot> --view activity`.
4. Presentera resultatet på enkel svenska enligt steg 5 i huvudskillen – behåll alla fakta, översätt
   tekniska commit-meddelanden, hitta aldrig på aktivitet och redovisa information som saknas.
