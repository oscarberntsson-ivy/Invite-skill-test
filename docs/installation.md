# Installation

Monitorn består av skills, Python-kod och inställningar som ska ligga tillsammans. Starta därför
Claude Code i projektmappen. Det räcker inte att kopiera skill-mapparna till `~/.claude/skills/`.

## Det här behövs

- **Claude Code**: `npm install -g @anthropic-ai/claude-code` (kräver Node.js 18 eller senare).
- **Python 3.9 eller senare** (`python3 --version`). Inga extra paket behövs.
- **macOS, Linux eller WSL på Windows.** Spärren körs som ett Unix-kommando.
- **Git** behövs bara för att hämta och uppdatera koden. Du kan också ladda ner den som ZIP från
  GitHub (Code → Download ZIP).

## Steg för steg

1. Hämta koden. Den ligger än så länge på en branch, inte på `main`:
   ```bash
   git clone -b claude/github-repo-monitor-mcp-zuul3l https://github.com/oscarberntsson-ivy/Invite-skill-test.git
   cd Invite-skill-test
   ```
2. Sätt GitHub-token (se [mcp-konfiguration.md](mcp-konfiguration.md) för behörigheter):
   ```bash
   export GITHUB_PERSONAL_ACCESS_TOKEN=github_pat_...
   ```
   Lägg raden i `~/.zshrc` eller `~/.bashrc`, så att du slipper göra om det varje gång.
3. Ställ in repot och templaten för inbjudningar. Det görs en gång:
   ```bash
   python3 -m repo_monitor issue configure \
     --repository din-org/ditt-repo \
     --template-path .github/ISSUE_TEMPLATE/din-template.yml \
     --enable
   ```
4. Starta Claude Code i mappen:
   ```bash
   claude
   ```
   Godkänn mappen och MCP-servern `github`. Kontrollera med `/mcp` att `github` är ansluten. Skriv
   `/` för att se kommandona, till exempel `/bjud-in-kandidat` och `/repo-monitor-all`.
5. Kontrollera installationen (valfritt): `python3 -m unittest discover -s tests`

## Uppdatera

`git pull` i mappen, eller ladda ner en ny ZIP. Inställningarna i `repo-monitor/*.json` är det enda
du behöver spara undan. Någon annan data finns inte lokalt.
