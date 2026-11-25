# Hur kandidater och repos hittas

Inget register sparas. Varje gång du frågar om en kandidat, eller om alla, gör agenten så här:

1. Läser **inbjudnings-issuerna** i det konfigurerade repot via GitHub MCP (`list_issues`). Varje
   issue innehåller kandidatens **namn** och **GitHub-användarnamn**, eftersom den skapades med
   templaten.
2. Söker efter repos som heter **`ivy-engineering-challenge-<github-användarnamn>`**
   (`search_repositories`), om verktyget finns.
3. Kopplar ihop person, användarnamn och repo med `python3 -m repo_monitor people`.

Resultatet visar också:
- inbjudningar där repot inte hittades. GitHub Action kan ha misslyckats eller inte körts än.
- repos som saknar inbjudnings-issue. Där visas bara användarnamnet.
- issues där inget användarnamn kunde läsas. Då stämmer troligen inte fältnamnen (se nedan).

Sökningen bryr sig inte om versaler, så "anna", "Anna" och "@anna-a" fungerar. Den bryr sig inte
heller om accenter, så "Asa" hittar "Åsa". Finns flera issues för samma användarnamn gäller den senaste.

Exempel med data från GitHub på stdin:

```bash
python3 -m repo_monitor people --query "Anna" <<'JSON'
{"issues": <svaret från list_issues>, "repos": <svaret från search_repositories eller null>}
JSON
```

## Inställningar (`repo-monitor/discovery.json`)

| Fält | Standard | Betydelse |
|---|---|---|
| `owner` | `IvyTechSE` | Organisationen där kandidaternas repos skapas |
| `repo_name_pattern` | `^ivy-engineering-chall[ae]nge-(?P<username>…)$` | Känner igen repo-namn och plockar ut användarnamnet. Både *challenge* och *challange* godtas. |
| `repo_name_template` | `ivy-engineering-challenge-{username}` | Räknar ut repo-namnet från en issue när repo-sökning saknas |
| `issues_repository` | *(samma som för inbjudningar)* | Repot där inbjudnings-issuerna finns |
| `issue_labels` | `[]` | Om ifyllt räknas bara issues med någon av dessa labels |
| `issue_fields.name` | `Namn`, `Name`, … | Template-fältets label för namnet |
| `issue_fields.github_username` | `GitHub-användarnamn`, `GitHub username`, … | Template-fältets label för användarnamnet |
| `automation_accounts` | `[]` | Konton (t.ex. en bot) vars commits inte räknas som kandidatens arbete |

Ändra med kommandot nedan. Agenten ändrar aldrig inställningarna själv.

```bash
python3 -m repo_monitor discover configure \
  --name-field "Ditt namn" --username-field "Ditt GitHub-användarnamn" \
  --labels invite-candidate --automation-accounts min-bot
```
