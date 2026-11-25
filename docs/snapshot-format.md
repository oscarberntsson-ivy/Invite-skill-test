# Snapshot-format

En snapshot är det JSON-dokument som Claude sätter ihop av GitHub MCP-svaren och skickar till
`python3 -m repo_monitor analyze` på **stdin**. Inget sparas på disk. Exempel:

```bash
python3 -m repo_monitor analyze --view candidate --since 2026-11-20 <<'JSON'
{ …snapshot… }
JSON
```

Flera repos skickas till `overview` som en JSON-lista med snapshots. Skapa en tom mall med:

```bash
python3 -m repo_monitor template ägare/namn
```

## Grundregel: `null` och `[]` betyder olika saker

| Värde | Betyder |
|---|---|
| `[]` (tom lista) | Data hämtades, och det finns inget, till exempel inga pull requests |
| `null` eller fältet saknas | Data **kunde inte hämtas**, och resultatet blir *okänt* |

Det är så monitorn skiljer på *ingen aktivitet* och *saknad information*.

## Fält

```jsonc
{
  "fetched_at": "2026-11-24T12:00:00Z",
  "access": {"ok": true, "error": null},     // ok=false => EJ TILLGÄNGLIGT
  "person": {                                 // valfritt: kandidaten (snapshot_person från `people`)
    "name": "Anna Andersson", "username": "anna-a",
    "issue_number": 12, "issue_url": "https://github.com/…/issues/12", "invited_at": "2026-11-25T08:00:00Z"
  },
  "repo": {                                   // search_repositories-objekt eller förenklat
    "owner": "org",                           // sträng eller {"login": "org"}; alternativt "full_name"
    "name": "repo",
    "html_url": "https://github.com/org/repo",
    "created_at": "2026-11-10T08:00:00Z",
    "pushed_at": "2026-11-23T16:42:10Z",      // senaste push (null om okänt)
    "default_branch": "main"
  },
  "branches": [{"name": "main", "commit": {"sha": "..."}}],   // list_branches; eller ["main", ...]
  "commits_by_branch": {                      // list_commits per gren; dubbletter slås ihop på SHA
    "main": [ {"sha": "...", "commit": {"message": "...", "author": {"name": "...", "date": "..."}},
               "author": {"login": "..."}, "parents": [...], "files": [{"filename": "..."}]} ]
  },
  "commits": [],                              // alternativ: platt lista (kan kombineras)
  "pull_requests": [ /* list_pull_requests-objekt */ ],
  "errors": [{"what": "pull requests", "message": "timeout"}]
}
```

## Förenklat commit-format

Det går också att använda ett förenklat format:

```json
{"sha": "abc…", "author": "anna", "author_name": "Anna A", "date": "2026-11-20T10:00:00Z",
 "message": "Add login", "branches": ["main"], "files": ["src/login.js"], "parent_count": 1}
```

## Klassificering

- **Startcommit (uppsättning):** författaren finns i `automation_accounts`, eller så är det den äldsta
  commiten och den gjordes högst 10 minuter efter att repositoryt skapades.
- **Merge-commit:** två eller fler föräldrar (`parents`). Den räknas separat och inte som kodbidrag.
- **Kodcommit:** alla övriga commits. Det är dessa som avgör kodstatusen.
- **Push:** räknas som aktivitet om `pushed_at` är mer än 10 minuter efter skapandet.
