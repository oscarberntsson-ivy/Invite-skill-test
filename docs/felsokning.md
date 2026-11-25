# Felsökning

## MCP-anslutningen

| Symptom | Trolig orsak | Åtgärd |
|---|---|---|
| `/mcp` visar inte `github` | `.mcp.json` har inte godkänts | Starta om Claude Code i projektmappen och godkänn servern. Kontrollera att `.claude/settings.json` innehåller `"enabledMcpjsonServers": ["github"]`. |
| `github` visas som *failed* | Token saknas eller är fel | `echo ${GITHUB_PERSONAL_ACCESS_TOKEN:0:11}` ska visa `github_pat_`. Sätt variabeln och starta om Claude Code. |
| `401 Unauthorized` | Token är ogiltig eller har gått ut | Skapa en ny token (se [mcp-konfiguration.md](mcp-konfiguration.md)). |
| `403 Forbidden` eller `Resource not accessible` | Token saknar behörighet till repositoryt, eller organisationen har inte godkänt token | Lägg till repositoryt i tokenens *Repository access*, ge *Contents* och *Pull requests: Read*, och be organisationsägaren godkänna token. |
| `404 Not Found` | Fel namn, privat repository utan åtkomst, eller borttaget repository | Kontrollera namnet. För en kandidat kan repot saknas om GitHub Action inte har körts än. GitHub svarar 404, inte 403, för privata repositories du saknar åtkomst till. |
| `409 Git Repository is empty` | Repositoryt har inga commits | Inget fel. Rapporteras som 0 commits (INAKTIVT). |
| `search_repositories` saknas | Toolset `repos` är inte aktiverat, eller servern har inte verktyget | Kontrollera `X-MCP-Toolsets`. Skapandedatum och senaste push blir då okända, och repos räknas fram från inbjudnings-issuerna. |
| Docker-varianten startar inte | Docker körs inte, eller imagen kan inte hämtas | Kör `docker pull ghcr.io/github/github-mcp-server`, och vid fel `docker logout ghcr.io`. |

Snabbtest i Claude Code: be Claude *"anropa get_me i GitHub MCP"*. Svaret ska visa ditt GitHub-konto.

## Vad rapporterna betyder när något saknas

- **EJ TILLGÄNGLIGT / Okänt:** repot kunde inte läsas alls. Det betyder **inte** att kandidaten är
  inaktiv. Har kandidaten bjudits in nyligen har repot kanske inte skapats än.
- **OKÄNT:** en del av datan, till exempel commits eller pull requests, kunde inte hämtas. Rapporten
  listar vad som saknas under *⚠️ Information som inte kunde hämtas*.
- **En kandidat hittas inte:** inbjudnings-issuen saknas, eller så kunde användarnamnet inte läsas ur
  den. Kontrollera `issue_fields` i `repo-monitor/discovery.json` (se [hitta-kandidater.md](hitta-kandidater.md)).

## Felmeddelanden från `repo_monitor`

Verktyget skriver begripliga fel på stderr och avslutas med kod 2, till exempel:

- `Snapshot saknas: skicka den på stdin …`: agenten skickade ingen data. Fråga igen.
- `Snapshot är inte giltig JSON (rad X…)`: datan blev trasig. Fråga igen.
- `'…' ser inte ut som ett repository.` Använd formatet `ägare/namn`.
- `Filen … är skadad och kunde inte läsas.`: en inställningsfil är trasig. Återställ den med git
  (`git checkout -- repo-monitor/`) eller skapa om inställningarna med `issue configure` och
  `discover configure`.

Monitorn sparar ingen data lokalt, så det finns ingen historik eller cache att rensa.
