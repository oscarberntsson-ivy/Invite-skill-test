# Installerar skillen "kodutmaning" for Claude Code (Windows PowerShell).
#
#   irm https://raw.githubusercontent.com/oscarberntsson-ivy/Invite-skill-test/claude/github-repo-monitor-mcp-zuul3l/install.ps1 | iex
#
# Avinstallera:  $env:KODUTMANING_UNINSTALL=1; irm .../install.ps1 | iex
#
# Gor:
#   1. hamtar skillen till %USERPROFILE%\.claude\skills\kodutmaning (behaller ifylld konfiguration)
#   2. fragar efter inbjudnings-repo och template om konfigurationen inte ar ifylld
#   3. lagger till GitHub-kopplingen (GitHub MCP) for alla mappar
#   4. lagger till skyddsregler i %USERPROFILE%\.claude\settings.json (tar inte bort nagot befintligt)
# Token skrivs aldrig ut och sparas bara i Claude Codes egen installningsfil (~\.claude.json).

$ErrorActionPreference = 'Stop'
& {
    $Source   = if ($env:KODUTMANING_SOURCE) { $env:KODUTMANING_SOURCE } else { 'https://raw.githubusercontent.com/oscarberntsson-ivy/Invite-skill-test/claude/github-repo-monitor-mcp-zuul3l' }
    $Home_    = $env:USERPROFILE
    $SkillDir = Join-Path $Home_ '.claude\skills\kodutmaning'
    $Settings = Join-Path $Home_ '.claude\settings.json'
    $Files    = 'SKILL.md', 'bjud-in.md', 'uppfoljning.md', 'konfiguration.md'
    $McpUrl   = 'https://api.githubcopilot.com/mcp/'
    $Utf8     = New-Object System.Text.UTF8Encoding $false

    function Fail($msg) { Write-Host ""; Write-Host "Fel: $msg" -ForegroundColor Red; throw "Installationen avbröts." }
    function ReadText($p) { [System.IO.File]::ReadAllText($p, [System.Text.Encoding]::UTF8) }
    function WriteText($p, $t) { [System.IO.File]::WriteAllText($p, $t, $Utf8) }
    function NeedsConfig($p) { (Test-Path $p) -and ((ReadText $p) -match 'GARE/REPO') }

    if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
        Fail 'Claude Code är inte installerat. Installera först: npm install -g @anthropic-ai/claude-code'
    }

    # --- Avinstallation ----------------------------------------------------
    if ($env:KODUTMANING_UNINSTALL) {
        if (Test-Path $SkillDir) { Remove-Item -Recurse -Force $SkillDir }
        & claude mcp remove github --scope user *> $null
        Write-Host 'Skillen och GitHub-kopplingen är borttagna.'
        Write-Host "Skyddsreglerna i $Settings finns kvar; ta bort dem för hand om du vill."
        return
    }

    # --- 1. Hamta skillen --------------------------------------------------
    Write-Host '1/4  Hämtar skillen…'
    $tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("kodutmaning-" + [guid]::NewGuid())
    New-Item -ItemType Directory -Force $tmp | Out-Null
    try {
        foreach ($f in $Files) {
            try {
                Invoke-WebRequest -UseBasicParsing -Uri "$Source/.claude/skills/kodutmaning/$f" -OutFile (Join-Path $tmp $f)
            } catch { Fail "kunde inte hämta $f från GitHub." }
        }
        New-Item -ItemType Directory -Force $SkillDir | Out-Null
        $existing = Join-Path $SkillDir 'konfiguration.md'
        if ((Test-Path $existing) -and -not (NeedsConfig $existing)) {
            Copy-Item $existing (Join-Path $tmp 'konfiguration.md') -Force
            Write-Host '     Behåller din befintliga konfiguration.'
        }
        Copy-Item (Join-Path $tmp '*.md') $SkillDir -Force
    } finally {
        Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
    }

    # --- 2. Konfiguration --------------------------------------------------
    Write-Host '2/4  Konfiguration…'
    $konf = Join-Path $SkillDir 'konfiguration.md'
    if (NeedsConfig $konf) {
        $repo = (Read-Host '     Inbjudnings-repo, där issues skapas (ägare/repo)').Trim()
        if ($repo -notmatch '^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$') { Fail "'$repo' ser inte ut som ägare/repo." }
        $tpl = (Read-Host '     Sökväg till issue-templaten (t.ex. .github/ISSUE_TEMPLATE/bjud-in.yml)').Trim()
        if ($tpl -notmatch '\.(yml|yaml|md)$') { Fail 'templaten måste vara en .yml-, .yaml- eller .md-fil.' }
        $org = (Read-Host '     Organisation för kandidaternas repos [IvyTechSE]').Trim()
        if (-not $org) { $org = 'IvyTechSE' }
        if ($org -notmatch '^[A-Za-z0-9_.-]+$') { Fail "'$org' ser inte ut som ett organisationsnamn." }
        $lines = (ReadText $konf) -split "`r?`n"
        $out = foreach ($l in $lines) {
            if     ($l.StartsWith('| Inbjudnings-repo')) { '| Inbjudnings-repo (där issues skapas) | `' + $repo + '` |' }
            elseif ($l.StartsWith('| Issue-template'))   { '| Issue-template i inbjudnings-repot | `' + $tpl + '` |' }
            elseif ($l.StartsWith('| Organisation'))     { '| Organisation där kandidaternas repos skapas | `' + $org + '` |' }
            else { $l }
        }
        WriteText $konf (($out -join "`n"))
        Write-Host "     Sparat i $konf"
    } else {
        Write-Host '     Redan ifylld.'
    }

    # --- 3. GitHub-koppling ------------------------------------------------
    Write-Host '3/4  GitHub-koppling…'
    $token = $env:GITHUB_PERSONAL_ACCESS_TOKEN
    if (-not $token) {
        $sec = Read-Host '     Klistra in din GitHub-token (github_pat_…, syns inte när du klistrar)' -AsSecureString
        $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
        try { $token = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
        finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
    }
    $token = "$token".Trim()
    if ($token -notmatch '^(github_pat_|ghp_)') {
        Fail 'det ser inte ut som en GitHub-token (ska börja med github_pat_). Se docs/installation.md.'
    }
    & claude mcp remove github --scope user *> $null
    & claude mcp add --transport http --scope user github $McpUrl --header "Authorization: Bearer $token" *> $null
    $ok = $LASTEXITCODE -eq 0
    $token = $null
    if (-not $ok) { Fail 'kunde inte lägga till GitHub-kopplingen (claude mcp add).' }

    # --- 4. Skyddsregler ---------------------------------------------------
    Write-Host '4/4  Skyddsregler…'
    New-Item -ItemType Directory -Force (Split-Path $Settings) | Out-Null
    $t = { param($n) "mcp__github__$n" }
    $add = [ordered]@{
        allow = @('get_me', 'get_file_contents', 'get_label', 'list_issues', 'issue_read', 'list_branches',
                  'list_commits', 'get_commit', 'list_pull_requests', 'pull_request_read') | ForEach-Object { & $t $_ }
        ask   = @(& $t 'issue_write')
        deny  = (@('create_or_update_file', 'push_files', 'delete_file', 'create_branch', 'create_repository',
                   'fork_repository', 'merge_pull_request', 'create_pull_request', 'update_pull_request',
                   'update_pull_request_branch', 'pull_request_review_write', 'add_issue_comment',
                   'update_issue_comment', 'sub_issue_write', 'actions_run_trigger') | ForEach-Object { & $t $_ }) +
                @('Edit(~/.claude/skills/kodutmaning/konfiguration.md)',
                  'Write(~/.claude/skills/kodutmaning/konfiguration.md)')
    }
    $s = $null
    if (Test-Path $Settings) {
        $raw = ReadText $Settings
        if ($raw.Trim()) {
            try { $s = $raw | ConvertFrom-Json }
            catch { Write-Host "     Kunde inte läsa $Settings (ogiltig JSON) – ingenting ändrat."; $s = 'skip' }
        }
    }
    if ($s -ne 'skip') {
        if (-not $s) { $s = New-Object PSObject }
        if (-not $s.PSObject.Properties['permissions']) { $s | Add-Member -NotePropertyName permissions -NotePropertyValue (New-Object PSObject) }
        foreach ($k in $add.Keys) {
            $cur = @()
            if ($s.permissions.PSObject.Properties[$k]) { $cur = @($s.permissions.$k) }
            $merged = @($cur) + @($add[$k] | Where-Object { $cur -notcontains $_ })
            if ($s.permissions.PSObject.Properties[$k]) { $s.permissions.$k = $merged }
            else { $s.permissions | Add-Member -NotePropertyName $k -NotePropertyValue $merged }
        }
        WriteText $Settings (($s | ConvertTo-Json -Depth 20) + "`n")
    }

    Write-Host ''
    Write-Host "Klart! Öppna ett nytt terminalfönster, starta 'claude' i valfri mapp och skriv t.ex.:"
    Write-Host '   Bjud in Anna Andersson till kodutmaningen'
    Write-Host '   Har Anna committat något?'
    Write-Host 'Kontrollera GitHub-kopplingen med /mcp inne i Claude Code.'
}
