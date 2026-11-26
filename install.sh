#!/usr/bin/env bash
# Installerar skillen "kodutmaning" för Claude Code (macOS, Linux, WSL).
#
#   curl -fsSL https://raw.githubusercontent.com/oscarberntsson-ivy/Invite-skill-test/claude/github-repo-monitor-mcp-zuul3l/install.sh | bash
#
# Avinstallera:  ... | bash -s -- --uninstall
#
# Gör:
#   1. hämtar skillen till ~/.claude/skills/kodutmaning (behåller din ifyllda konfiguration)
#   2. frågar efter inbjudnings-repo och template om konfigurationen inte är ifylld
#   3. lägger till GitHub-kopplingen (GitHub MCP) för alla mappar
#   4. lägger till skyddsregler i ~/.claude/settings.json (utan att ta bort något befintligt)
# Token skrivs aldrig ut och sparas bara i Claude Codes egen inställningsfil (~/.claude.json).

set -euo pipefail

SOURCE="${KODUTMANING_SOURCE:-https://raw.githubusercontent.com/oscarberntsson-ivy/Invite-skill-test/claude/github-repo-monitor-mcp-zuul3l}"
SKILL_DIR="$HOME/.claude/skills/kodutmaning"
SETTINGS="$HOME/.claude/settings.json"
FILES="SKILL.md bjud-in.md uppfoljning.md konfiguration.md"
MCP_URL="https://api.githubcopilot.com/mcp/"
TTY_IN="${KODUTMANING_TTY_IN:-/dev/tty}"    # frågor läses från terminalen även vid "curl | bash"
TTY_OUT="${KODUTMANING_TTY_OUT:-/dev/tty}"

say()  { printf '%s\n' "$*"; }
fail() { printf '\nFel: %s\n' "$*" >&2; exit 1; }
open_tty() { [ -n "${TTY_OPEN:-}" ] || { exec 3<"$TTY_IN" || fail "ingen terminal att fråga i."; TTY_OPEN=1; }; }
ask()  { local v; open_tty; printf '%s' "$1" >"$TTY_OUT"; IFS= read -r v <&3 || true; printf '%s' "$v"; }
ask_secret() {
  local v; open_tty; printf '%s' "$1" >"$TTY_OUT"
  stty -echo <&3 2>/dev/null || true
  IFS= read -r v <&3 || true
  stty echo <&3 2>/dev/null || true
  printf '\n' >"$TTY_OUT"; printf '%s' "$v"
}

command -v claude >/dev/null 2>&1 || fail "Claude Code är inte installerat. Installera först: npm install -g @anthropic-ai/claude-code"

# --- Avinstallation --------------------------------------------------------
if [ "${1:-}" = "--uninstall" ]; then
  rm -rf "$SKILL_DIR"
  claude mcp remove github --scope user >/dev/null 2>&1 || true
  say "Skillen och GitHub-kopplingen är borttagna."
  say "Skyddsreglerna i $SETTINGS finns kvar; ta bort dem för hand om du vill."
  exit 0
fi

command -v curl >/dev/null 2>&1 || fail "curl saknas."

# --- 1. Hämta skillen ------------------------------------------------------
say "1/4  Hämtar skillen…"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
for f in $FILES; do
  curl -fsSL "$SOURCE/.claude/skills/kodutmaning/$f" -o "$tmp/$f" || fail "kunde inte hämta $f från GitHub."
done
mkdir -p "$SKILL_DIR"
if [ -f "$SKILL_DIR/konfiguration.md" ] && ! grep -q 'GARE/REPO' "$SKILL_DIR/konfiguration.md"; then
  cp "$SKILL_DIR/konfiguration.md" "$tmp/konfiguration.md"
  say "     Behåller din befintliga konfiguration."
fi
cp "$tmp"/*.md "$SKILL_DIR/"

# --- 2. Konfiguration ------------------------------------------------------
say "2/4  Konfiguration…"
if grep -q 'GARE/REPO' "$SKILL_DIR/konfiguration.md"; then
  open_tty
  repo="$(ask '     Inbjudnings-repo, där issues skapas (ägare/repo): ')"
  [[ "$repo" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]] || fail "'$repo' ser inte ut som ägare/repo."
  tpl="$(ask '     Sökväg till issue-templaten (t.ex. .github/ISSUE_TEMPLATE/bjud-in.yml): ')"
  [[ "$tpl" =~ \.(yml|yaml|md)$ ]] || fail "templaten måste vara en .yml-, .yaml- eller .md-fil."
  org="$(ask '     Organisation för kandidaternas repos [IvyTechSE]: ')"
  org="${org:-IvyTechSE}"
  [[ "$org" =~ ^[A-Za-z0-9_.-]+$ ]] || fail "'$org' ser inte ut som ett organisationsnamn."
  out="$tmp/konf.md"
  : >"$out"
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in
      "| Inbjudnings-repo"*) printf '| Inbjudnings-repo (där issues skapas) | `%s` |\n' "$repo" >>"$out" ;;
      "| Issue-template"*)   printf '| Issue-template i inbjudnings-repot | `%s` |\n' "$tpl" >>"$out" ;;
      "| Organisation"*)     printf '| Organisation där kandidaternas repos skapas | `%s` |\n' "$org" >>"$out" ;;
      *)                     printf '%s\n' "$line" >>"$out" ;;
    esac
  done <"$SKILL_DIR/konfiguration.md"
  cp "$out" "$SKILL_DIR/konfiguration.md"
  say "     Sparat i $SKILL_DIR/konfiguration.md"
else
  say "     Redan ifylld."
fi

# --- 3. GitHub-koppling ----------------------------------------------------
say "3/4  GitHub-koppling…"
token="${GITHUB_PERSONAL_ACCESS_TOKEN:-}"
if [ -z "$token" ]; then
  open_tty
  token="$(ask_secret '     Klistra in din GitHub-token (github_pat_…, syns inte när du klistrar): ')"
fi
case "$token" in
  github_pat_*|ghp_*) ;;
  *) fail "det ser inte ut som en GitHub-token (ska börja med github_pat_). Se docs/installation.md." ;;
esac
claude mcp remove github --scope user >/dev/null 2>&1 || true
claude mcp add --transport http --scope user github "$MCP_URL" \
  --header "Authorization: Bearer $token" >/dev/null 2>&1 \
  || fail "kunde inte lägga till GitHub-kopplingen (claude mcp add)."
unset token

# --- 4. Skyddsregler -------------------------------------------------------
say "4/4  Skyddsregler…"
mkdir -p "$(dirname "$SETTINGS")"
if command -v node >/dev/null 2>&1; then
  node - "$SETTINGS" <<'JS'
const fs = require("fs");
const path = process.argv[2];
let s = {};
if (fs.existsSync(path)) {
  try { s = JSON.parse(fs.readFileSync(path, "utf8") || "{}"); }
  catch (e) { console.error("     Kunde inte läsa " + path + " (ogiltig JSON) – ingenting ändrat."); process.exit(0); }
}
const t = (n) => "mcp__github__" + n;
const add = {
  allow: ["get_me", "get_file_contents", "get_label", "list_issues", "issue_read", "list_branches",
          "list_commits", "get_commit", "list_pull_requests", "pull_request_read"].map(t),
  ask: [t("issue_write")],
  deny: ["create_or_update_file", "push_files", "delete_file", "create_branch", "create_repository",
         "fork_repository", "merge_pull_request", "create_pull_request", "update_pull_request",
         "update_pull_request_branch", "pull_request_review_write", "add_issue_comment",
         "update_issue_comment", "sub_issue_write", "actions_run_trigger"].map(t)
         .concat(["Edit(~/.claude/skills/kodutmaning/konfiguration.md)",
                  "Write(~/.claude/skills/kodutmaning/konfiguration.md)"]),
};
s.permissions = s.permissions || {};
for (const k of Object.keys(add)) {
  const cur = Array.isArray(s.permissions[k]) ? s.permissions[k] : [];
  s.permissions[k] = cur.concat(add[k].filter((x) => !cur.includes(x)));
}
fs.writeFileSync(path, JSON.stringify(s, null, 2) + "\n");
JS
elif [ ! -f "$SETTINGS" ]; then
  curl -fsSL "$SOURCE/settings.user.json" -o "$SETTINGS" || say "     Kunde inte hämta skyddsreglerna."
else
  say "     Node.js saknas, så $SETTINGS kunde inte uppdateras automatiskt."
  say "     Lägg in reglerna från settings.user.json i repot för hand (se docs/installation.md)."
fi

say ""
say "Klart! Öppna en ny terminal, starta 'claude' i valfri mapp och skriv t.ex.:"
say "   Bjud in Anna Andersson till kodutmaningen"
say "   Har Anna committat något?"
say "Kontrollera GitHub-kopplingen med /mcp inne i Claude Code."
