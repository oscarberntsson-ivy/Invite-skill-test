# Skapa issue från den konfigurerade templaten

Repository Monitor kan skapa **en sorts issue**: i **ett** bestämt repository och enligt **en**
bestämd issue-template. Issuen används för att trigga en GitHub Action, till exempel repo-flödet som
skapar repositories och bjuder in contributors.

Det här är det enda monitorn får skriva till GitHub. Allt annat är fortfarande bara läsning.

## Så används det

Fråga Claude, eller använd kommandot:

```
/bjud-in-kandidat Anna Andersson, anna-a
```

Agenten gör följande:

1. Kontrollerar konfigurationen.
2. Hämtar templaten från repositoryt. Det kontrollerar samtidigt att repositoryt finns och går att läsa.
3. Läser templatens fält och frågar efter de uppgifter som saknas.
4. Kontrollerar att templatens labels finns i repositoryt, och vilka som kan tilldelas (assignees).
5. Visar ett **utkast**: repository, template, titel, labels, assignees och den exakta beskrivningen.
6. Frågar **"Vill du att jag skapar denna issue?"**.
7. Efter ditt ja frågar Claude Code en gång till och visar repository och titel.
8. Skapar issuen och svarar med länken.

## Konfigurera (när du har uppgifterna)

Konfigurationen finns i `repo-monitor/issue-config.json`. Funktionen är **avstängd** tills den är
ifylld. Fyll i den med ett kommando:

```bash
python3 -m repo_monitor issue configure \
  --repository min-org/repo-flode \
  --template-path .github/ISSUE_TEMPLATE/nytt-repo.yml \
  --enable
```

Kontrollera resultatet:

```bash
python3 -m repo_monitor issue config
```

| Fält | Betydelse | Exempel |
|---|---|---|
| `enabled` | Måste vara `true` för att issues ska kunna skapas | `true` |
| `repository` | Det **enda** repository där issues får skapas | `min-org/repo-flode` |
| `template_path` | Sökväg till templaten i det repositoryt (`.yml`, `.yaml` eller `.md`) | `.github/ISSUE_TEMPLATE/nytt-repo.yml` |
| `template_ref` | Valfri gren eller tagg att läsa templaten från (standard: huvudgrenen) | `main` |
| `title` | Valfri fast titel. Ersätter templatens titel. | `Skapa repo` |
| `extra_labels` | Valfria extra labels utöver templatens. Måste finnas i repositoryt. | `["automation"]` |
| `default_assignees` | Valfria assignees. Tas bort om de inte kan tilldelas. | `["oscar"]` |
| `milestone` | Valfri milestone (nummer eller titel). Måste finnas. | `2` |

Andra flaggor till `issue configure`: `--template-ref`, `--title`, `--labels a,b`, `--assignees a,b`,
`--milestone`, `--disable`.

> Agenten ändrar aldrig konfigurationen själv. Claude Code frågar alltid innan `issue configure`
> körs, och direkta filändringar av konfigurationen är spärrade.

## Token och MCP-server

Issuen skapas med samma GitHub MCP-server (`github`) som används för all annan kommunikation med
GitHub. Någon extra server eller token behövs inte.

1. Token (`GITHUB_PERSONAL_ACCESS_TOKEN`, se [mcp-konfiguration.md](mcp-konfiguration.md)) behöver
   **Issues: Read and write** på det konfigurerade repositoryt, utöver läsbehörigheterna.
2. Toolset `issues` måste vara aktiverat (`X-MCP-Toolsets` i `.mcp.json`). Det är det redan.
3. Kontrollera med `/mcp` i Claude Code att servern `github` är ansluten.

GitHub Action triggas av att issuen skapas, oavsett vem som skapar den. Om workflowen kontrollerar
*vem* som skapat issuen (till exempel `github.event.issue.user.login` eller `author_association`) måste
tokenens ägare uppfylla det villkoret.

## Skydd

| Skydd | Var |
|---|---|
| Bara `issue_write` med `method: create`. Befintliga issues ändras aldrig. | Spärren `.claude/hooks/issue_guard.py` |
| Bara det konfigurerade repositoryt | Spärren |
| Bara exakt det innehåll som visats i ett sparat utkast | Spärren jämför titel, beskrivning, labels, assignees och milestone |
| Samma utkast kan inte skapas två gånger | Spärren och PostToolUse-hooken |
| Claude Code frågar alltid innan issuen skickas | `ask` i `.claude/settings.json` och spärrens beslut `ask` |
| `issue_write` är det enda skrivverktyget som tillåts. Det kräver alltid bekräftelse. | `ask` på `mcp__github__issue_write`, `deny` på alla andra skrivverktyg |
| Kommentarer, sub-issues och andra skrivverktyg är spärrade | `deny` i `.claude/settings.json` |
| Templates, konfiguration, utkast och spärren kan inte ändras av agenten | `deny` på Edit/Write |
| Labels och milestones måste finnas i repositoryt | `issue draft` stoppar utkastet annars |
| Templatens struktur måste följas | `issue draft` underkänner egna fält och saknade rubriker |
| Fel i spärren nekar alltid | Spärren är "fail closed" |

## Templateformat som stöds

- **YAML issue forms** (`.yml` och `.yaml`): fälttyperna `input`, `textarea`, `dropdown` (även med
  flera val), `checkboxes` och `markdown`. `markdown` visas inte i issuen, precis som på GitHub.
  Beskrivningen byggs i exakt samma format som GitHubs webbformulär (`### Label` följt av svaret, och
  `_No response_` för tomma fält). Det gör att GitHub Actions som läser issue forms fungerar.
- **Markdown-templates** (`.md`) med front matter (`name`, `about`, `title`, `labels`, `assignees`).
  Agenten fyller i text under templatens rubriker. Rubrikerna och deras ordning behålls.

PyYAML används om det finns installerat. Annars används en inbyggd tolk.

## Felsökning

| Symptom | Åtgärd |
|---|---|
| "Issue-funktionen är inte konfigurerad" | Kör `issue configure` (se ovan). |
| Templaten kunde inte hämtas (404) | Kontrollera `repository`, `template_path` och `template_ref`, och att `GITHUB_PERSONAL_ACCESS_TOKEN` kan läsa repositoryt. |
| "Labeln … finns inte" | Skapa labeln i repositoryt eller ändra `extra_labels`. Templatens labels kan behövas för att workflowen ska triggas. |
| `mcp__github__issue_write` saknas | Kontrollera med `/mcp` att `github` är ansluten, att `X-MCP-Toolsets` innehåller `issues`, och att `X-MCP-Readonly` *inte* är satt. Utkastet är sparat. |
| 403 när issuen skapas | Token saknar *Issues: Read and write* på det konfigurerade repositoryt. |
| "Innehållet matchar inget godkänt utkast" | Utkastet ändrades efter att det visades. Skapa ett nytt utkast. |
| GitHub Action startade inte | Kontrollera i repositoryts Actions-flik att workflowen lyssnar på `issues: [opened]` (eller `labeled`) och att eventuella villkor på label och titel uppfylls. |

Visa sparade utkast: `python3 -m repo_monitor issue list`.
