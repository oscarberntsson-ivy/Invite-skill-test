---
name: repo-monitor-all
description: "/repo-monitor:all – Sammanfattar samtliga registrerade repositories i en översikt: vilka som är aktiva, påbörjade, inaktiva, under granskning eller inte tillgängliga."
argument-hint: ""
disable-model-invocation: true
allowed-tools: mcp__github__get_me, mcp__github__search_repositories, mcp__github__list_commits, mcp__github__get_commit, mcp__github__list_branches, mcp__github__list_pull_requests, mcp__github__pull_request_read, Bash(python3 -m repo_monitor:*), Read, Write(repo-monitor/snapshots/**)
---

# /repo-monitor:all

Sammanfattar samtliga registrerade repositories i en översikt: vilka som är aktiva, påbörjade, inaktiva, under granskning eller inte tillgängliga.

Läs och följ arbetsflödet i `.claude/skills/repo-monitor/SKILL.md` med **läge `all`**.

Synkronisera först registret från beställnings-issues (och repo-sökning) enligt steg 1 i huvudskillen. Hämta sedan data för **varje** repository i `repo-monitor/registry.json` (ett i taget). Repositories som inte kan läsas ska ändå ingå, med `"access": {"ok": false, ...}`. Är registret tomt: förklara hur projekt registreras (se `docs/registrera-repositories.md`).

Kort sammanfattning av flödet:
1. Hämta data via GitHub MCP (endast läsverktyg) enligt steg 2 i huvudskillen.
2. Skriv snapshot till `repo-monitor/snapshots/ÄGARE__NAMN.json`.
3. Kör `python3 -m repo_monitor overview <alla snapshots>`.
4. Presentera resultatet på enkel svenska enligt steg 5 i huvudskillen – behåll alla fakta, översätt
   tekniska commit-meddelanden, hitta aldrig på aktivitet och redovisa information som saknas.
