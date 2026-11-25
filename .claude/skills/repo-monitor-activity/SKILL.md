---
name: repo-monitor-activity
description: "/repo-monitor:activity – Visar senaste aktiviteten i en kandidats repo som en tidslinje: commits, push, pull requests och merges."
argument-hint: "namn, GitHub-användarnamn eller ägare/repo"
disable-model-invocation: true
allowed-tools: mcp__github__get_me, mcp__github__search_repositories, mcp__github__list_commits, mcp__github__get_commit, mcp__github__list_branches, mcp__github__list_pull_requests, mcp__github__pull_request_read, mcp__github__list_issues, Bash(python3 -m repo_monitor:*)
---

# /repo-monitor:activity

Visar senaste aktiviteten i en kandidats repo som en tidslinje: commits, push, pull requests och merges.

Följ arbetsflödet i `.claude/skills/repo-monitor/SKILL.md` med **läge `activity`**.

Kandidat eller repo: `$ARGUMENTS`. Är det ett namn eller GitHub-användarnamn: hitta kandidaten (steg A i huvudskillen, `--query`). Är det tomt: fråga vilken kandidat som avses. Hämta sedan data (steg B) och kör `python3 -m repo_monitor analyze --view activity` med snapshoten på stdin.

All data hämtas från GitHub via GitHub MCP (endast läsverktyg) och skickas till verktyget på stdin.
Inget sparas lokalt. Presentera resultatet på enkel svenska enligt steg D i huvudskillen: behåll alla
fakta, översätt tekniska commit-meddelanden, hitta aldrig på aktivitet och redovisa information som saknas.
