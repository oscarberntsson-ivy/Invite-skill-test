# Installation

Skillen `kodutmaning` består bara av textfiler (Markdown). Den kräver inga program, inget Python och
inget git. Det som behövs är Claude och en koppling till GitHub (GitHub MCP).

## 0. Konfigurera skillen (en gång, av den som administrerar)

Öppna `.claude/skills/kodutmaning/konfiguration.md` och fyll i:
- **inbjudnings-repot**, där inbjudningarna skapas som issues, och
- **sökvägen till issue-templaten**.

Kontrollera också organisationen och fältnamnen.

## Alternativ A: Claude i webbläsaren eller desktop-appen (ingen installation)

Fungerar enligt Claudes hjälpcenter på alla planer, även Free. Det som krävs:
- **Kodkörning** måste vara påslagen, eftersom skills kräver det. På Free, Pro och Max slår du på
  det under *Settings → Capabilities*. På Team och Enterprise styr administratören det.
- **Egen koppling (custom connector):** Free får ha en, vilket räcker för GitHub. På Team och
  Enterprise kan bara ägare (Owners) lägga till kopplingar.

1. **Ladda upp skillen.**
   - Ladda ner mappen `.claude/skills/kodutmaning` från GitHub: *Code → Download ZIP*, packa upp
     och ta ut mappen `kodutmaning`.
   - Komprimera **mappen** till `kodutmaning.zip`: högerklicka och välj "Komprimera" eller "Skicka
     till → Komprimerad mapp". Mappen ska ligga överst i ZIP-filen, med `kodutmaning/SKILL.md` inuti.
   - I Claude: *Customize → Skills* (i äldre versioner *Settings → Capabilities → Skills*), ladda
     upp ZIP-filen och slå på skillen.
   - I Team och Enterprise kan en administratör lägga in skillen åt hela organisationen.
2. **Koppla GitHub.**
   - I Claude: *Settings → Connectors → Add custom connector*.
   - URL: `https://api.githubcopilot.com/mcp/`
   - Under *Request headers*: `Authorization` = `Bearer <din GitHub-token>`. Se tokenkraven nedan.
   - Ställ in att Claude alltid ska fråga innan skrivverktyg används, särskilt `issue_write`.
3. Skriv till exempel *"Bjud in Anna Andersson till kodutmaningen"* eller *"Har Anna committat något?"*.

> Om kopplingen inte går att lägga till med en token: GitHubs MCP-server och claude.ai har inte
> bekräftat att inloggning fungerar mellan dem. Använd då alternativ B.

## Alternativ B: Claude Code

1. Hämta mappen (`git clone -b claude/github-repo-monitor-mcp-zuul3l https://github.com/oscarberntsson-ivy/Invite-skill-test.git`,
   eller ladda ner som ZIP).
2. Sätt token: `export GITHUB_PERSONAL_ACCESS_TOKEN=github_pat_...`
3. Starta `claude` i mappen och godkänn MCP-servern `github`. Kontrollera med `/mcp`.
4. Skillen laddas automatiskt. Du kan också skriva `/kodutmaning`.

`.mcp.json` och `.claude/settings.json` i mappen kopplar GitHub och blockerar skrivverktyg utom
`issue_write`. Claude Code frågar alltid innan `issue_write` används.

## GitHub-token

Skapa en **fine-grained personal access token** (GitHub → Settings → Developer settings):

| Inställning | Värde |
|---|---|
| Resource owner | Organisationen där kandidaternas repos och inbjudnings-repot finns |
| Repository access | De repos som behövs, eller *All repositories* för organisationen |
| Metadata | Read-only |
| Contents | Read-only |
| Pull requests | Read-only |
| Issues | **Read and write** (för att skapa inbjudningar) |
| Expiration | Sätt ett utgångsdatum |

Ge inga andra behörigheter. Lägg aldrig token i filer som delas.
