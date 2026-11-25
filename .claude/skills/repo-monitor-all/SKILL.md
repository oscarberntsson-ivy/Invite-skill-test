---
name: repo-monitor-all
description: "/repo-monitor:all – Sammanfattar alla kandidaters challenge-repositories i en översikt: vilka som är aktiva, påbörjade, inaktiva, under granskning eller inte tillgängliga."
argument-hint: ""
disable-model-invocation: true
allowed-tools: mcp__github__get_me, mcp__github__search_repositories, mcp__github__list_commits, mcp__github__get_commit, mcp__github__list_branches, mcp__github__list_pull_requests, mcp__github__pull_request_read, mcp__github__list_issues, Bash(python3 -m repo_monitor:*)
---

# /repo-monitor:all

Sammanfattar alla kandidaters challenge-repositories i en översikt: vilka som är aktiva, påbörjade, inaktiva, under granskning eller inte tillgängliga.

Följ arbetsflödet i `.claude/skills/repo-monitor/SKILL.md` med **läge `all`**.

Hitta **alla** kandidater (steg A i huvudskillen), hämta data för varje kandidats repo (steg B) och kör `python3 -m repo_monitor overview` med alla snapshots som en JSON-lista på stdin.

All data hämtas från GitHub via GitHub MCP (endast läsverktyg) och skickas till verktyget på stdin.
Inget sparas lokalt. Presentera resultatet på enkel svenska enligt steg D i huvudskillen: behåll alla
fakta, översätt tekniska commit-meddelanden, hitta aldrig på aktivitet och redovisa information som saknas.
