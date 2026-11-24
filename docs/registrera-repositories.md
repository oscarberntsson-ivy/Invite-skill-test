# Registrera repositories

Monitorn vet vilka projekt som tillhör systemet genom registret `repo-monitor/registry.json`.

## Varför ett eget register?

När monitorn byggdes fanns ingen kod för repo-flödet i det här repositoryt, och ingen befintlig
metadata att återanvända. Därför används ett enkelt JSON-register. Det går att läsa och redigera för
hand och kan versionshanteras med git. Flödet ändras **inte** automatiskt. Kopplingen nedan är ett
förslag som du själv väljer att införa.

## Automatiskt: namnstandard och beställnings-issues (rekommenderat)

Repositories som ska följas heter **`ivy-engineering-challenge-<github-användarnamn>`**. Varje repo
beställs genom en issue som skapas med templaten (se [skapa-issue.md](skapa-issue.md)), och issuen
innehåller personens namn och GitHub-användarnamn. Monitorn använder detta för att:

- hitta alla challenge-repositories,
- koppla varje repo till en **person**, så att du kan fråga "hur går det för Anna?",
- visa personens namn i rapporterna i stället för bara användarnamnet,
- hitta beställningar där repot saknas (GitHub Action kan ha misslyckats).

Agenten synkroniserar automatiskt innan `/repo-monitor-all`. Manuellt:

```bash
# issues.json = svaret från list_issues, repos.json = svaret från search_repositories (valfritt)
python3 -m repo_monitor discover sync --issues issues.json --repos repos.json
python3 -m repo_monitor registry find "Anna"
```

### Inställningar (`repo-monitor/discovery.json`)

| Fält | Standard | Betydelse |
|---|---|---|
| `owner` | `IvyTechSE` | Organisationen där repona skapas |
| `repo_name_pattern` | `^ivy-engineering-chall[ae]nge-(?P<username>…)$` | Känner igen repo-namn och plockar ut användarnamnet. Tål båda stavningarna *challenge* och *challange*. |
| `repo_name_template` | `ivy-engineering-challenge-{username}` | Används för att räkna ut repo-namnet från en issue när repo-sökning inte finns |
| `issues_repository` | *(samma som i issue-config)* | Repot där beställnings-issues skapas |
| `issue_labels` | `[]` | Bara issues med någon av dessa labels räknas (tom = alla issues med användarnamn) |
| `issue_fields.name` | `Namn`, `Name`, … | Template-fältets label för personens namn |
| `issue_fields.github_username` | `GitHub-användarnamn`, `GitHub username`, … | Template-fältets label för GitHub-användarnamnet |

Ändra med till exempel:

```bash
python3 -m repo_monitor discover configure --owner IvyTechSE \
  --name-template "ivy-engineering-challenge-{username}" \
  --name-field "Ditt namn" --username-field "Ditt GitHub-användarnamn" --labels create-repo
```

Fältnamnen ska vara exakt de labels som står i templaten. Versaler och accenter spelar ingen roll.
Finns flera issues för samma användarnamn används den senaste.

## Vad som sparas per repository

| Fält | Beskrivning | Källa |
|---|---|---|
| `owner` | Organisation eller konto | registrering |
| `name` | Repository-namn | registrering |
| `url` | Repository-URL | registrering, uppdateras vid kontroll |
| `project_name` | Läsbart projektnamn i rapporter | registrering |
| `created_at` | Skapandedatum | registrering, uppdateras från GitHub vid kontroll |
| `invited_contributors` | GitHub-användare som bjudits in (via issue) | registrering |
| `invitation_issue` | Nummer på inbjudnings-issuet (valfritt) | registrering |
| `contributors` | Personer som faktiskt bidragit med kod | uppdateras vid kontroll |
| `last_activity` | Senaste aktivitet | uppdateras vid kontroll |
| `last_checked_at` | Senaste lyckade kontroll | uppdateras vid kontroll |
| `source` | `automation`, `manual` eller `discovered` | registrering |
| `person_name` | Personens namn från beställnings-issuen | synkronisering |
| `github_username` | Användarnamnet (från issuen eller repo-namnet) | synkronisering |
| `invitation_issue_url` / `invited_at` | Länk till och datum för beställningen | synkronisering |
| `repo_verified` | `true` om repot hittades, `false` om det saknas | synkronisering |

`automation_accounts` (överst i filen) listar konton som repo-flödet använder, till exempel en bot.
Commits från dessa konton räknas som automatisk uppsättning och inte som bidrag. Sätt dem med:

```bash
python3 -m repo_monitor registry set-automation min-bot,annan-bot
```

## Kommandon

```bash
# Lägg till (eller uppdatera) ett projekt
python3 -m repo_monitor registry add min-org/mitt-projekt \
  --project-name "Mitt projekt" --created-at 2026-11-24 \
  --invited anna,erik --issue 1 --source automation

# Det går också att använda en URL
python3 -m repo_monitor registry add https://github.com/min-org/mitt-projekt

python3 -m repo_monitor registry list          # lista alla projekt
python3 -m repo_monitor registry show min-org/mitt-projekt
python3 -m repo_monitor registry remove min-org/mitt-projekt   # historiken sparas
```

Du kan också be Claude: *"Registrera min-org/mitt-projekt, inbjudna är anna och erik."*

## Koppla in det automatiserade repo-flödet (förslag)

Välj det alternativ som passar flödets arkitektur.

**A. Flödet körs där det här repositoryt finns (script eller Claude Code-skill).** Lägg till ett steg
direkt efter att repositoryt och inbjudnings-issuet har skapats:

```bash
python3 -m repo_monitor registry add "$OWNER/$REPO" \
  --created-at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --invited "$INVITED_USERS" --issue "$ISSUE_NUMBER" --source automation
```

Committa sedan `repo-monitor/registry.json`.

**B. Flödet körs någon annanstans (till exempel GitHub Actions i ett annat repository).** Låt flödet
sätta ett *topic* på varje repository som skapas, till exempel `repo-monitor`. Be sedan Claude:
*"Leta efter nya projekt med topic repo-monitor i min-org."* Claude söker med `search_repositories`
(läsning), visar de projekt som inte finns i registret och frågar innan de läggs till.

**C. Manuellt.** Registrera projekten med kommandona ovan.

Projekt som inte finns i registret kan ändå analyseras. Rapporten påminner då om att projektet bör
registreras.
