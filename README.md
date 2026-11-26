# Kodutmaningen – bjud in kandidater och följ upp

En skill för Claude som gör två saker, utan att du behöver kunna GitHub:

1. **Bjuda in kandidater:** Claude ställer frågorna från issue-templaten och skapar en GitHub-issue.
   Issuen startar en GitHub Action som skapar kandidatens repo `ivy-engineering-challenge-<användarnamn>`.
2. **Följa upp:** Claude svarar på om en kandidat har committat något, och kan visa en översikt
   över alla kandidater.

**Lättviktigt:** skillen består bara av textfiler. Den kräver ingen installation, inget Python och
inget git. Allt hämtas från GitHub via GitHub MCP varje gång, och inget sparas.

## Exempel

```
Du:      Bjud in Anna Andersson till kodutmaningen
Claude:  ställer templatens frågor (namn, GitHub-användarnamn, …)
Du:      svarar
Claude:  kontrollerar att Anna inte redan är inbjuden, visar ett utkast:
         "Vill du att jag skapar denna issue?"
Du:      ja
Claude:  skapar issuen och skickar länken. GitHub Action skapar repot och bjuder in Anna.

Du:      Har Anna committat något?
Claude:  Ja – Anna Andersson (anna-a) har gjort 3 commits i IvyTechSE/ivy-engineering-challenge-anna-a,
         senast 24 november 2026.

Du:      Har hon committat något sedan i måndags?
Claude:  Ja – … Sedan 23 november 2026: 1 commit.

Du:      Hur går det för alla kandidater?
Claude:  en tabell med status, antal commits, senaste commit och öppna pull requests.
```

## Kom igång

**Claude Code: ett kommando.** Skriptet installerar skillen för alla mappar och frågar efter din GitHub-token:

```powershell
# Windows (PowerShell)
irm https://raw.githubusercontent.com/oscarberntsson-ivy/Invite-skill-test/claude/github-repo-monitor-mcp-zuul3l/install.ps1 | iex
```
```bash
# macOS / Linux
curl -fsSL https://raw.githubusercontent.com/oscarberntsson-ivy/Invite-skill-test/claude/github-repo-monitor-mcp-zuul3l/install.sh | bash
```

**claude.ai eller desktop-appen:** ladda upp mappen `kodutmaning` som ZIP under *Skills*, och lägg
till GitHub som anpassad koppling (`https://api.githubcopilot.com/mcp/`).

Detaljer, tokenkrav och avinstallation finns i [docs/installation.md](docs/installation.md).
Fyll gärna i [`konfiguration.md`](.claude/skills/kodutmaning/konfiguration.md) i repot först, så
slipper användarna svara på frågor om repo och template.

## Innehåll

| Fil | Innehåll |
|---|---|
| `.claude/skills/kodutmaning/SKILL.md` | Skillen: när den används och regler |
| `.claude/skills/kodutmaning/konfiguration.md` | Inbjudnings-repo, template, organisation och fältnamn |
| `.claude/skills/kodutmaning/bjud-in.md` | Så bjuds en kandidat in (frågor, utkast, issue) |
| `.claude/skills/kodutmaning/uppfoljning.md` | Så besvaras "har kandidaten committat något?" och översikten |
| `install.ps1`, `install.sh` | Installation för Claude Code med ett kommando |
| `settings.user.json` | Skyddsreglerna (används av installationen och vid manuell installation) |
| `.mcp.json`, `.claude/settings.json` | För Claude Code när man kör i repo-mappen |
| `docs/` | Installation och felsökning |

## Säkerhet

- Det enda Claude får skriva till GitHub är en **ny issue i inbjudnings-repot**, och bara efter ditt
  uttryckliga ja till ett utkast. Claude frågar dessutom innan verktyget används.
- Allt annat är bara läsning. I Claude Code är skrivverktygen dessutom blockerade i `.claude/settings.json`.
- Token anges i GitHub-kopplingen eller som miljövariabel, aldrig i skillens filer.
