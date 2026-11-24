# GitHub Repository Monitor

En AI-baserad monitor i **Claude Code** som följer de GitHub-repositories som skapas av det
automatiserade repo-flödet. Den förklarar på **enkel svenska** vad som händer i projekten, så att du
inte behöver kunna GitHub eller programmering.

Du kan till exempel fråga:

- *Har någon börjat arbeta med projektet?*
- *När skedde senaste pushen?*
- *Vilka har bidragit, och vad har de gjort?*
- *Vad har förändrats sedan förra kontrollen?*
- *Vilka projekt är fortfarande inaktiva?*

Monitorn har två ansvarsområden:

1. **Monitorering:** läsa, analysera och sammanfatta aktivitet i GitHub-repositories. Här görs
   enbart läsning.
2. **Issue Management:** skapa en issue i **ett** konfigurerat repository med **en** konfigurerad
   template. Issuen triggar en GitHub Action. Agenten visar alltid ett utkast och skapar issuen
   först efter ditt godkännande. Se [docs/skapa-issue.md](docs/skapa-issue.md).

## Så fungerar det

```
 Du (fråga eller kommando)
        │
        ▼
 Claude Code ── skill: .claude/skills/repo-monitor ──┐
        │                                            │
        │ 1. hämtar data (ENDAST läsning)            │ 3. översätter tekniska
        ▼                                            │    meddelanden till svenska
 GitHub MCP (officiell server, read-only)            │
        │                                            │
        ▼ 2. snapshot (JSON)                         │
 python3 -m repo_monitor ── status, contributors, ───┘
                            förändringar, rapport
        │
        ▼
 repo-monitor/  registry.json · state/ (historik) · reports/ (rapporter)
```

- **GitHub MCP** är den enda datakällan. Den körs i läsläge, och skrivverktyg är dessutom blockerade
  i `.claude/settings.json`.
- **`repo_monitor`** (Python, bara standardbiblioteket) räknar fram status, contributors och
  förändringar på ett deterministiskt sätt. Siffrorna gissas aldrig av AI:n.
- **Claude** hämtar data, kör analysen och förklarar resultatet på vardaglig svenska.

## Kom igång

1. Skapa en GitHub-token med **läsbehörighet** och sätt den som miljövariabel (se
   [docs/mcp-konfiguration.md](docs/mcp-konfiguration.md)):
   ```bash
   export GITHUB_PERSONAL_ACCESS_TOKEN=github_pat_...
   ```
2. Starta Claude Code i den här mappen och godkänn MCP-servern `github` (kontrollera med `/mcp`).
3. Registrera de projekt som ska följas (se [docs/registrera-repositories.md](docs/registrera-repositories.md)):
   ```bash
   python3 -m repo_monitor registry add min-org/mitt-projekt --project-name "Mitt projekt" --invited anna,erik
   ```
4. Fråga Claude, eller använd ett kommando:
   ```
   /repo-monitor-all
   ```

## Kommandon

| Önskat kommando | Kommando i Claude Code | Vad det gör | Sparar kontroll? |
|---|---|---|---|
| `/repo-monitor:status` | `/repo-monitor-status ägare/repo` | Status för ett projekt | Nej |
| `/repo-monitor:all` | `/repo-monitor-all` | Översikt över alla registrerade projekt | Ja |
| `/repo-monitor:activity` | `/repo-monitor-activity ägare/repo` | Tidslinje över senaste händelser | Nej |
| `/repo-monitor:contributors` | `/repo-monitor-contributors ägare/repo` | Vem har bidragit med vad | Nej |
| `/repo-monitor:changes` | `/repo-monitor-changes ägare/repo` | Vad som ändrats sedan förra kontrollen | Ja |
| `/repo-monitor:report` | `/repo-monitor-report ägare/repo` | Fullständig statusrapport (sparas i `repo-monitor/reports/`) | Ja |
| – | `/repo-monitor-create-issue beskrivning` | Skapar en issue från den konfigurerade templaten, efter utkast och godkännande | – |

> **Varför bindestreck i stället för kolon?** Projektets egna kommandon i Claude Code (skills) får bara
> innehålla små bokstäver, siffror och bindestreck. Kolon (`namn:kommando`) används bara för kommandon
> från installerade plugins. Därför heter kommandona `/repo-monitor-status` och så vidare. Du kan också
> skriva `/repo-monitor status ägare/repo` eller ställa frågan med vanliga ord. Huvudskillen
> `repo-monitor` används då automatiskt.

En **kontroll** (`changes`, `report`, `all`) sparar nuläget som jämförelsepunkt. Första gången blir
resultatet en **baslinje**. Därefter visas vad som har hänt sedan den senaste kontrollen.

## Statusrapporter

Varje rapport innehåller:

- **Projektinformation:** projektnamn, repository och skapandedatum.
- **Aktivitet:** antal commits, antal contributors, senaste aktivitet, senaste push, senaste
  contributor, öppna och mergade pull requests samt grenar.
- **Statusbedömning** i två delar, eftersom statusarna kan överlappa:

| Kodstatus | Betyder |
|---|---|
| INAKTIVT | Ingen kod från contributors. Automatiska startfiler räknas inte. |
| PÅBÖRJAT | Minst en kodcommit. |
| AKTIVT | Minst två contributors, eller commits på minst två olika dagar. |
| OKÄNT | Commits kunde inte hämtas. Det är *inte* samma sak som inaktivt. |
| EJ TILLGÄNGLIGT | Repositoryt kunde inte läsas, till exempel på grund av behörighet. |

| Granskningsstatus | Betyder |
|---|---|
| UNDER GRANSKNING | Det finns öppna pull requests. |
| MERGAT | Minst en pull request har mergats till målgrenen. |
| INGA PULL REQUESTS | Inga förslag på ändringar har skapats. |

- **Vad betyder det?** och **Nästa steg**, i enkel svenska.
- **Förändringar sedan förra kontrollen**, eller en tydlig markering att det är en baslinje.
- **Ordlista** för de tekniska orden.
- **⚠️ Information som inte kunde hämtas**, om något saknas.

Monitorn skiljer på *repository skapat*, *commit*, *push*, *pull request skapad* och *mergad*. Kod på
en sidogren räknas inte som mergad, och en öppen pull request räknas inte som godkänd.

## Filer

| Sökväg | Innehåll |
|---|---|
| `.mcp.json` | MCP-servrarna `github` (read-only) och `github-issues` (bara issues, separat token) |
| `.claude/settings.json` | Tillåtna läsverktyg, blockerade skrivverktyg och hooks |
| `.claude/hooks/issue_guard.py` | Spärr: issues skapas bara i det konfigurerade repot och bara enligt ett godkänt utkast |
| `repo-monitor/issue-config.json` | Konfiguration för issue-skapande (repository och template) |
| `repo-monitor/issue-drafts/` | Sparade utkast och skapade issues |
| `.claude/skills/repo-monitor/SKILL.md` | Huvudskillen: hela arbetsflödet och reglerna |
| `.claude/skills/repo-monitor-*/SKILL.md` | De sex kommandona |
| `repo_monitor/` | Analys, statusmodell, historik och svenska rapporter |
| `repo-monitor/registry.json` | Register över projekt som följs |
| `repo-monitor/state/` | Historik per repository: senaste kontroll, kända commit-SHA:er, PR-status och grenar |
| `repo-monitor/reports/` | Sparade rapporter (`latest.md` och en fil per tidpunkt) |
| `repo-monitor/snapshots/` | Tillfällig rådata från MCP (ignoreras av git) |
| `tests/` | Tester med mockad GitHub-data |
| `docs/` | Konfiguration, registrering, snapshot-format och felsökning |

## Tester

```bash
python3 -m unittest discover -s tests -v
```

Testerna täcker: repository utan commits, med en commit, med flera contributors, med flera grenar,
med öppna och mergade pull requests, utan ny aktivitet sedan förra kontrollen, repository som inte är
tillgängligt, flera repositories med olika aktivitetsnivåer, delvis saknad data samt normalisering av
MCP:s råformat.

## Dokumentation

- [MCP-konfiguration och behörigheter](docs/mcp-konfiguration.md)
- [Registrera repositories (och koppla in repo-flödet)](docs/registrera-repositories.md)
- [Snapshot-format](docs/snapshot-format.md)
- [Skapa issue från templaten](docs/skapa-issue.md)
- [Felsökning](docs/felsokning.md)
