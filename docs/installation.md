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

## Alternativ B: Claude Code – ett kommando (rekommenderas)

Kräver bara att [Claude Code](https://docs.claude.com/en/docs/claude-code) är installerat och att du
har en GitHub-token (se nedan). Skriptet installerar skillen **personligt**, så att den fungerar i
alla mappar.

**Windows (PowerShell):**
```powershell
irm https://raw.githubusercontent.com/oscarberntsson-ivy/Invite-skill-test/claude/github-repo-monitor-mcp-zuul3l/install.ps1 | iex
```

**macOS / Linux / WSL (Terminal):**
```bash
curl -fsSL https://raw.githubusercontent.com/oscarberntsson-ivy/Invite-skill-test/claude/github-repo-monitor-mcp-zuul3l/install.sh | bash
```

Skriptet gör följande:
1. Hämtar skillen till `~/.claude/skills/kodutmaning`. Git behövs inte.
2. Frågar efter inbjudnings-repo och template, om `konfiguration.md` inte redan är ifylld i repot.
   Är den ifylld blir det inga frågor.
3. Frågar efter din GitHub-token med dold inmatning och lägger till GitHub-kopplingen för alla
   mappar. Ingen miljövariabel behövs. Token sparas i Claude Codes egen fil `~/.claude.json`.
4. Lägger till skyddsreglerna i `~/.claude/settings.json`, utan att ta bort något du redan har där:
   - Läsverktygen tillåts utan att Claude frågar.
   - Claude frågar alltid innan en issue skapas.
   - Alla andra skrivverktyg blockeras, också i dina andra projekt.

Starta sedan `claude` i valfri mapp och kontrollera kopplingen med `/mcp`.

- **Uppdatera:** kör samma kommando igen. Din ifyllda konfiguration behålls.
- **Byta token:** kör kommandot igen och klistra in den nya.
- **Avinstallera:**
  - Windows: `$env:KODUTMANING_UNINSTALL=1; irm https://raw.githubusercontent.com/oscarberntsson-ivy/Invite-skill-test/claude/github-repo-monitor-mcp-zuul3l/install.ps1 | iex`
  - macOS och Linux: `curl -fsSL https://raw.githubusercontent.com/oscarberntsson-ivy/Invite-skill-test/claude/github-repo-monitor-mcp-zuul3l/install.sh | bash -s -- --uninstall`

  Skyddsreglerna i `~/.claude/settings.json` ligger kvar. Ta bort dem för hand om du vill.

> **Tips för administratören:** fyll i `konfiguration.md` i repot innan andra installerar. Då
> behöver användarna bara klistra in sin token.

### Manuellt, i repo-mappen (utan skript)

1. Hämta mappen (`git clone -b claude/github-repo-monitor-mcp-zuul3l https://github.com/oscarberntsson-ivy/Invite-skill-test.git`,
   eller ladda ner som ZIP).
2. Sätt token som miljövariabel `GITHUB_PERSONAL_ACCESS_TOKEN`.
3. Starta `claude` i mappen och godkänn MCP-servern `github`. `.mcp.json` och
   `.claude/settings.json` i mappen kopplar GitHub och lägger in skyddsreglerna.

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
