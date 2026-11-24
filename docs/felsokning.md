# Felsökning

## MCP-anslutningen

| Symptom | Trolig orsak | Åtgärd |
|---|---|---|
| `/mcp` visar inte `github` | `.mcp.json` har inte godkänts | Starta om Claude Code i projektmappen och godkänn servern. Kontrollera att `.claude/settings.json` innehåller `"enabledMcpjsonServers": ["github"]`. |
| `github` visas som *failed* | Token saknas eller är fel | `echo ${GITHUB_PERSONAL_ACCESS_TOKEN:0:11}` ska visa `github_pat_`. Sätt variabeln och starta om Claude Code. |
| `401 Unauthorized` | Token är ogiltig eller har gått ut | Skapa en ny token (se [mcp-konfiguration.md](mcp-konfiguration.md)). |
| `403 Forbidden` eller `Resource not accessible` | Token saknar behörighet till repositoryt, eller organisationen har inte godkänt token | Lägg till repositoryt i tokenens *Repository access*, ge *Contents* och *Pull requests: Read*, och be organisationsägaren godkänna token. |
| `404 Not Found` | Fel namn, privat repository utan åtkomst, eller borttaget repository | Kontrollera namnet med `python3 -m repo_monitor registry show ägare/namn`. GitHub svarar 404, inte 403, för privata repositories du saknar åtkomst till. |
| `409 Git Repository is empty` | Repositoryt har inga commits | Inget fel. Rapporteras som 0 commits (INAKTIVT). |
| `search_repositories` saknas | Toolset `repos` är inte aktiverat, eller servern har inte verktyget | Kontrollera `X-MCP-Toolsets`. Skapandedatum hämtas då från registret och senaste push blir okänd. |
| Docker-varianten startar inte | Docker körs inte, eller imagen kan inte hämtas | Kör `docker pull ghcr.io/github/github-mcp-server`, och vid fel `docker logout ghcr.io`. |

Snabbtest i Claude Code: be Claude *"anropa get_me i GitHub MCP"*. Svaret ska visa ditt GitHub-konto.

## Vad rapporterna betyder när något saknas

- **EJ TILLGÄNGLIGT:** repositoryt kunde inte läsas alls. Det betyder **inte** att projektet är
  inaktivt. Historiken skrivs inte över, och rapporten visar senaste lyckade kontroll.
- **OKÄNT:** en del av datan, till exempel commits eller pull requests, kunde inte hämtas. Rapporten
  listar vad som saknas under *⚠️ Information som inte kunde hämtas*. Jämförelsen med förra
  kontrollen anger att den delen inte kunde kontrolleras, och den sparade historiken för den delen
  behålls.

## Felmeddelanden från `repo_monitor`

Verktyget skriver begripliga fel på stderr och avslutas med kod 2, till exempel:

- `Snapshot-filen … finns inte.` Hämtningen sparade ingen fil. Kör kommandot igen.
- `Snapshot-filen … innehåller ogiltig JSON (rad X…)`. Snapshoten blev trasig. Kör hämtningen igen.
- `'…' ser inte ut som ett repository.` Använd formatet `ägare/namn`.
- `Filen … är skadad och kunde inte läsas.` Ett register eller en historikfil är trasig. Återställ den
  med git (`git checkout -- repo-monitor/registry.json`) eller ta bort historikfilen. Nästa kontroll
  blir då en ny baslinje.

## Återställa historiken

Ta bort `repo-monitor/state/ägare__namn.json`. Nästa kontroll blir en ny baslinje. Visa sparad
historik med `python3 -m repo_monitor state show ägare/namn`.
