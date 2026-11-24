# Konfigurera GitHub MCP

Monitorn använder GitHubs officiella MCP-server, [github/github-mcp-server](https://github.com/github/github-mcp-server).
Den konfigureras i `.mcp.json` i projektets rot och laddas automatiskt när Claude Code startas i mappen.

## 1. Skapa en token med enbart läsbehörighet

Använd en **fine-grained personal access token** (GitHub → Settings → Developer settings →
Personal access tokens → Fine-grained tokens):

| Inställning | Värde |
|---|---|
| Resource owner | Organisationen eller kontot där repo-flödet skapar repositories |
| Repository access | *All repositories* för ägaren, eller bara de repositories som ska följas |
| **Metadata** | Read-only (obligatoriskt) |
| **Contents** | Read-only (commits, grenar, filer) |
| **Pull requests** | Read-only |
| **Issues** | Read-only (valfritt, för inbjudnings-issues) |
| Expiration | Sätt ett utgångsdatum, till exempel 90 dagar |

Ge **inga** skrivbehörigheter. Om organisationen kräver godkännande av tokens måste en
organisationsägare godkänna den. Med en klassisk token behövs scope `repo` för privata repositories
eller `public_repo` för publika. Den ger dock skrivrätt, så fine-grained token rekommenderas.

## 2. Sätt token som miljövariabel

Lägg aldrig token i källkoden eller i `.mcp.json`. Sätt den i skalet innan du startar Claude Code:

```bash
export GITHUB_PERSONAL_ACCESS_TOKEN=github_pat_...
claude
```

Du kan också lägga den i en lokal fil som inte checkas in (`.env` ignoreras av git) och läsa in den
med `source .env`. `.mcp.json` hämtar värdet via `${GITHUB_PERSONAL_ACCESS_TOKEN}`.

## 3. Konfigurationen (`.mcp.json`)

```json
{
  "mcpServers": {
    "github": {
      "type": "http",
      "url": "https://api.githubcopilot.com/mcp/",
      "headers": {
        "Authorization": "Bearer ${GITHUB_PERSONAL_ACCESS_TOKEN}",
        "X-MCP-Readonly": "true",
        "X-MCP-Toolsets": "context,repos,pull_requests,issues"
      }
    }
  }
}
```

- `X-MCP-Readonly: true` gör att servern bara exponerar läsverktyg.
- `X-MCP-Toolsets` begränsar servern till de verktygsgrupper som behövs.

### Alternativ: lokal Docker i stället för GitHubs hostade server

```json
{
  "mcpServers": {
    "github": {
      "command": "docker",
      "args": ["run", "-i", "--rm",
               "-e", "GITHUB_PERSONAL_ACCESS_TOKEN", "-e", "GITHUB_TOOLSETS", "-e", "GITHUB_READ_ONLY",
               "ghcr.io/github/github-mcp-server"],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "${GITHUB_PERSONAL_ACCESS_TOKEN}",
        "GITHUB_TOOLSETS": "context,repos,pull_requests,issues",
        "GITHUB_READ_ONLY": "1"
      }
    }
  }
}
```

## 4. Dubbelt skydd i Claude Code (`.claude/settings.json`)

Utöver read-only-läget i servern gäller detta i `.claude/settings.json`:

- **`allow`:** läsverktygen (`list_commits`, `get_commit`, `list_branches`, `list_pull_requests`,
  `pull_request_read`, `search_repositories` med flera) och `python3 -m repo_monitor` körs utan att
  Claude frågar om lov varje gång.
- **`deny`:** alla skrivverktyg är blockerade, även om servern skulle exponera dem. Det gäller push,
  filändringar, nya grenar, att skapa, merga eller uppdatera pull requests, kommentarer, issues och
  att starta workflows.

> Deny-listan gäller hela projektet. Vill du någon gång skapa en pull request i *det här* repot via
> Claude måste du tillfälligt ta bort `mcp__github__create_pull_request` från listan, till exempel i
> `.claude/settings.local.json`.

## Verktyg som används

| Behov | MCP-verktyg |
|---|---|
| Inloggad användare och åtkomstkontroll | `get_me` |
| Repository-information (skapad, senaste push, huvudgren) | `search_repositories` (`repo:ägare/namn`) |
| Grenar | `list_branches` |
| Commits och författare | `list_commits` |
| Enskild commit med ändrade filer | `get_commit` |
| Pull requests | `list_pull_requests`, `pull_request_read` |
| Inbjudnings-issues (valfritt) | `list_issues`, `issue_read` |
