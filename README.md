# GitHub Repository Monitor – kodutmaningen

En AI-agent i **Claude Code** som gör två saker, utan att du behöver kunna GitHub:

1. **Bjuda in kandidater:** agenten ställer frågorna från issue-templaten och skapar en GitHub-issue.
   Issuen startar en GitHub Action som skapar kandidatens repo `ivy-engineering-challenge-<användarnamn>`.
2. **Följa upp:** agenten svarar på om en kandidat har committat något, och kan sammanfatta
   aktiviteten i alla kandidaters repos.

All kommunikation med GitHub går via **GitHub MCP**. **Inget sparas lokalt.** Agenten frågar GitHub
varje gång, och svaren bygger alltid på det som finns där just då.

## Flödet

```
Du:     "Bjud in Anna Andersson till kodutmaningen"            (eller /bjud-in-kandidat)
Agent:  ställer frågorna från issue-templaten (namn, GitHub-användarnamn, …)
Du:     svarar
Agent:  kontrollerar att Anna inte redan är inbjuden, visar ett utkast och frågar
        "Vill du att jag skapar denna issue?"
Du:     "ja"   (Claude Code visar anropet och frågar en gång till)
Agent:  skapar issuen och skickar länken. GitHub Action skapar repot och bjuder in Anna.

Senare:
Du:     "Har Anna committat något?"
Agent:  "Ja – Anna Andersson (anna-a) har gjort 2 commits i IvyTechSE/ivy-engineering-challenge-anna-a,
         senast 25 november 2026."
     eller "Nej – Anna Andersson (anna-a) har inte committat något … ännu."
     eller "Okänt – repot kunde inte läsas. Det har kanske inte skapats ännu."

Du:     "Har Anna committat något sedan i måndags?"
Agent:  "Ja – … Sedan 23 november 2026: 1 commit."
```

Agenten hittar kandidaten genom att läsa inbjudnings-issuerna på GitHub. Där står namn och
GitHub-användarnamn. Bara kandidatens egna commits räknas, inte automatiska startfiler eller
andras commits.

## Kommandon

Du kan alltid fråga med vanliga ord. Kommandona är genvägar.

| Kommando | Vad det gör |
|---|---|
| `/bjud-in-kandidat Anna Andersson` | Bjud in en kandidat (frågor, utkast, issue efter godkännande) |
| `/repo-monitor-all` | Översikt över alla kandidaters repos: aktiva, påbörjade, inaktiva och saknade |
| `/repo-monitor-status Anna` | Status för en kandidats repo, med vad det betyder och nästa steg |
| `/repo-monitor-activity Anna` | Tidslinje över senaste händelser |
| `/repo-monitor-contributors Anna` | Vem som har bidragit och med vad |
| `/repo-monitor-report Anna` | Fullständig statusrapport |

## Kom igång

Se [docs/installation.md](docs/installation.md). Kortversion:

```bash
git clone -b claude/github-repo-monitor-mcp-zuul3l https://github.com/oscarberntsson-ivy/Invite-skill-test.git && cd Invite-skill-test
export GITHUB_PERSONAL_ACCESS_TOKEN=github_pat_...
python3 -m repo_monitor issue configure --repository din-org/ditt-repo \
  --template-path .github/ISSUE_TEMPLATE/din-template.yml --enable
claude
```

## Så fungerar det

```
 Du ──► Claude Code (skills i .claude/skills/)
            │  1. hämtar data                       ▲ 3. svarar på enkel svenska
            ▼                                       │
        GitHub MCP (officiell server) ──► 2. data på stdin ──► python3 -m repo_monitor
                                                               (status, kandidat, rapport)
```

- **GitHub MCP** är den enda kopplingen till GitHub. Det enda skrivverktyget som får användas är
  `issue_write`, och bara för att skapa inbjudningar. Alla andra skrivverktyg är blockerade.
- **`repo_monitor`** (Python, bara standardbiblioteket) räknar fram status och svar på ett
  deterministiskt sätt, så siffrorna gissas aldrig. Det läser data på stdin, skriver svaret och
  sparar ingenting.
- **Inställningarna** är det enda som finns på disk:
  - `repo-monitor/issue-config.json`: vilket repo och vilken template inbjudningar skapas med.
  - `repo-monitor/discovery.json`: namnstandarden för repos och vilka template-fält som innehåller
    namn och användarnamn.

## Statusbedömning

| Kodstatus | Betyder |
|---|---|
| INAKTIVT | Ingen kod från kandidaten eller andra contributors. Automatiska startfiler räknas inte. |
| PÅBÖRJAT | Minst en kodcommit. |
| AKTIVT | Minst två contributors, eller commits på minst två olika dagar. |
| OKÄNT | Commits kunde inte hämtas. Det är *inte* samma sak som inaktivt. |
| EJ TILLGÄNGLIGT | Repot kunde inte läsas, till exempel för att det inte har skapats ännu. |

Granskningsstatus redovisas separat: **UNDER GRANSKNING** (öppna pull requests), **MERGAT** eller
**INGA PULL REQUESTS**.

## Säkerhet

- Issues kan bara skapas i det konfigurerade repot, och bara som *nya* issues. Det kontrolleras av
  spärren `.claude/hooks/issue_guard.py`.
- Agenten visar alltid ett utkast och väntar på ditt ja. Claude Code frågar sedan en gång till.
- Alla andra skrivverktyg är blockerade: push, filändringar, branches, pull requests och kommentarer.
- Token läses från miljövariabeln `GITHUB_PERSONAL_ACCESS_TOKEN`. Den ligger aldrig i koden.

## Filer

| Sökväg | Innehåll |
|---|---|
| `.mcp.json` | GitHub MCP-servern `github` |
| `.claude/settings.json` | Tillåtna läsverktyg, blockerade skrivverktyg och spärren |
| `.claude/hooks/issue_guard.py` | Spärr för att skapa issues |
| `.claude/skills/` | `bjud-in-kandidat`, `repo-monitor` och kommandona `repo-monitor-*` |
| `repo_monitor/` | Analys, statusmodell, template-tolkning och svenska rapporter |
| `repo-monitor/*.json` | Inställningar (se ovan) |
| `tests/` | Tester med mockad GitHub-data (`python3 -m unittest discover -s tests`) |
| `docs/` | Installation, MCP-konfiguration, inbjudningar, kandidater, snapshot-format och felsökning |

## Dokumentation

- [Installation](docs/installation.md)
- [MCP-konfiguration och behörigheter](docs/mcp-konfiguration.md)
- [Bjuda in kandidat (issue från templaten)](docs/skapa-issue.md)
- [Hur kandidater och repos hittas](docs/hitta-kandidater.md)
- [Snapshot-format](docs/snapshot-format.md)
- [Felsökning](docs/felsokning.md)
