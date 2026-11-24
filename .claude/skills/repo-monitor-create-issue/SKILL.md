---
name: repo-monitor-create-issue
description: Skapar en GitHub-issue i det ENDA konfigurerade repositoryt med den ENDA konfigurerade issue-templaten (issuen triggar en GitHub Action). Använd när användaren ber om att skapa/beställa en sådan issue. Visar alltid ett utkast och skapar issuen först efter uttryckligt godkännande.
argument-hint: "[beskrivning av vad issuen ska innehålla]"
allowed-tools: mcp__github__get_file_contents, mcp__github__get_label, mcp__github__list_repository_collaborators, mcp__github-issues__issue_write, Bash(python3 -m repo_monitor:*), Read, Write(repo-monitor/issue-work/**)
---

# Skapa issue från den konfigurerade templaten

Användarens önskemål: `$ARGUMENTS`

Detta är **det enda** som Repository Monitor får skriva till GitHub: en ny issue, i ett fast
repository, enligt en fast template. Issuen används för att trigga en GitHub Action, så innehållet
måste följa templaten exakt.

## Regler

- **Repository och template kommer bara från konfigurationen** (`repo-monitor/issue-config.json`).
  Om användaren nämner ett annat repository eller en annan template: förklara att funktionen bara
  är konfigurerad för det angivna repositoryt, och skapa ingenting.
- **Ändra aldrig konfigurationen själv.** `issue configure` körs bara om användaren uttryckligen ber om det.
- Ersätt eller utöka **aldrig** templaten med ett eget format. Lägg inte till egna fält eller rubriker.
- **Hitta inte på uppgifter.** Obligatoriska fält fylls bara med det användaren sagt. Fråga om
  resten. Du får formulera om användarens svar till tydlig text, men inte lägga till fakta
  (namn, användarnamn, datum, repo-namn och så vidare).
- Använd bara labels, assignees och milestones som har verifierats i repositoryt.
- **Skapa aldrig issuen utan uttryckligt godkännande** ("ja", "skapa", "godkänt") på *det senast
  visade* utkastet. Ändras något måste ett nytt utkast visas och godkännas.
- Ändra aldrig befintliga issues, templates eller andra filer i GitHub.
- En spärr (`.claude/hooks/issue_guard.py`) nekar allt som inte matchar konfigurationen och ett
  sparat utkast. Claude Code frågar dessutom användaren innan issuen skickas. Försök aldrig kringgå spärren.

## Arbetsflöde

1. **Kontrollera konfigurationen:** `python3 -m repo_monitor issue config`.
   Om status inte är "klar att använda": berätta på enkel svenska vad som saknas, visa kommandot ur
   `docs/skapa-issue.md` som användaren kan köra, och avsluta.
2. **Hämta templaten** (kontrollerar också att repositoryt finns och är tillgängligt):
   `mcp__github__get_file_contents` med `owner`/`repo` från konfigurationen, `path` = `template_path`
   och `ref` = `template_ref` om den är satt.
   - 404 eller 403: förklara att repositoryt eller templaten inte kunde läsas (fel namn, saknad
     behörighet för token) och avsluta. Gissa inte på en annan template.
   - Spara filinnehållet **oförändrat** med Write till `repo-monitor/issue-work/template.yml`
     (eller `template.md` för en Markdown-template).
3. **Läs fälten:** `python3 -m repo_monitor issue template repo-monitor/issue-work/template.yml`.
   Resultatet visar templatens namn, titel, labels och `questions` (fält-id, label, typ, obligatoriskt,
   val och beskrivning).
4. **Samla in information.** Använd det användaren redan sagt. Ställ frågor om allt som är
   obligatoriskt och saknas, helst alla på en gång. Använd fältens labels och beskrivningar, och
   förklara med enkla ord. För dropdowns och checkboxes: visa de tillåtna valen.
5. **Verifiera repo-uppgifter:**
   - Labels: kör `mcp__github__get_label` för varje label i templaten och i `extra_labels`.
   - Assignees, om några ska sättas: `mcp__github__list_repository_collaborators`.
   - Skriv resultatet till `repo-monitor/issue-work/meta.json`:
     `{"labels_existing": [...], "labels_missing": [...], "assignable": [... eller null], "milestones": null}`
     Sätt `milestones` till en lista med `{"number", "title"}` bara om du har kunnat hämta milestones.
6. **Skapa utkastet:** skriv svaren till `repo-monitor/issue-work/answers.json`. Nycklarna ska vara
   fält-id (eller label), och `title` om titeln ska anges. Värdena ska vara text, en lista för
   checkboxes eller dropdowns med flera val, eller `true` för att kryssa alla rutor. För
   Markdown-templates används rubriken som nyckel. Kör:
   `python3 -m repo_monitor issue draft --template-file repo-monitor/issue-work/template.yml --answers repo-monitor/issue-work/answers.json --repo-meta repo-monitor/issue-work/meta.json`
   - Slutkod 3: utkastet är inte klart. Fråga användaren om det som saknas, eller förklara
     problemet (till exempel en label som inte finns). Kör sedan om.
7. **Visa utkastet** för användaren precis som verktyget skrev det, och fråga
   **"Vill du att jag skapar denna issue?"** Vänta på svar.
8. **Efter uttryckligt ja:** hämta exakt payload med `python3 -m repo_monitor issue payload <utkast-id>`
   och anropa `mcp__github-issues__issue_write` med **exakt** de fälten (`method: "create"`, `owner`,
   `repo`, `title`, `body`, och i förekommande fall `labels`, `assignees`, `milestone`). Ändra ingenting.
9. **Svara med länken** till den skapade issuen. Förklara att GitHub Action nu bör starta i repositoryt.
   Om spärren inte hittade länken i svaret: kör `python3 -m repo_monitor issue record <utkast-id> --url <länk>`.
   Om GitHub svarade med fel: förklara felet enkelt och skapa inte issuen igen utan nytt godkännande.

## Om verktyget `mcp__github-issues__issue_write` saknas

Servern `github-issues` är inte ansluten. Använd **inte** något annat skrivverktyg. Förklara för
användaren att `GITHUB_ISSUES_TOKEN` och servern `github-issues` behöver konfigureras, och hänvisa till
`docs/skapa-issue.md`. Utkastet finns sparat och kan skapas senare.
