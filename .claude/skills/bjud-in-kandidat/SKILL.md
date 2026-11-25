---
name: bjud-in-kandidat
description: Bjuder in / lägger till en kandidat (person) till kodutmaningen på GitHub. Ställer frågorna från den konfigurerade issue-templaten, visar ett utkast och skapar – efter godkännande – en GitHub-issue i det ENDA konfigurerade repositoryt, vilket triggar en GitHub Action som skapar kandidatens repo. Använd när användaren vill bjuda in, lägga till eller beställa ett repo för en kandidat/person.
argument-hint: "[kandidatens namn och/eller GitHub-användarnamn]"
allowed-tools: mcp__github__get_file_contents, mcp__github__get_label, mcp__github__list_repository_collaborators, mcp__github-issues__issue_write, Bash(python3 -m repo_monitor:*), Read, Write(repo-monitor/issue-work/**)
---

# Bjud in kandidat till kodutmaningen

Användarens önskemål: `$ARGUMENTS`

Flödet:
1. Användaren ber om att bjuda in en kandidat.
2. Du svarar med templatens frågor.
3. Användaren svarar.
4. Du visar ett utkast.
5. Efter godkännande skapas issuen. GitHub Action skapar då kandidatens repo och bjuder in kandidaten.
6. Kandidaten följs sedan automatiskt av monitorn, så användaren kan fråga om kandidaten har committat något.

Detta är **det enda** som Repository Monitor får skriva till GitHub.

## Regler

- **Repository och template kommer bara från konfigurationen** (`repo-monitor/issue-config.json`).
  Nämner användaren ett annat repository eller en annan template: förklara att det inte går och skapa ingenting.
- **Ändra aldrig konfigurationen själv.** `issue configure` körs bara om användaren uttryckligen ber om det.
- Ersätt eller utöka **aldrig** templaten med ett eget format. Lägg inte till egna fält.
- **Hitta inte på uppgifter.** Obligatoriska fält fylls bara med det användaren har sagt.
  Gissa aldrig namn, GitHub-användarnamn eller e-post.
- Använd bara labels, assignees och milestones som har verifierats i repositoryt.
- **Skapa aldrig issuen utan uttryckligt godkännande** ("ja", "skapa", "godkänt") av det senast visade utkastet.
- En spärr (`.claude/hooks/issue_guard.py`) nekar allt som inte matchar konfigurationen och ett sparat utkast.
  Claude Code frågar dessutom användaren innan något skickas. Försök aldrig kringgå spärren.

## Arbetsflöde

1. **Konfiguration:** `python3 -m repo_monitor issue config`. Är den inte "klar att använda": förklara
   kort vad som saknas, hänvisa till `docs/skapa-issue.md` och avsluta.
2. **Hämta templaten:** `mcp__github__get_file_contents` med `owner`/`repo` från konfigurationen, `path` =
   `template_path` och `ref` = `template_ref` om den är satt. Vid 404 eller 403: förklara och avsluta.
   Spara innehållet **oförändrat** till `repo-monitor/issue-work/template.yml` (eller `.md`).
3. **Ställ frågorna:** `python3 -m repo_monitor issue questions repo-monitor/issue-work/template.yml`.
   Visa frågorna för användaren. Har användaren redan gett några svar (till exempel namnet i
   `$ARGUMENTS`): skriv vilka svar du redan har, och fråga bara efter resten. **Vänta på svar.**
4. **Verifiera labels** med `mcp__github__get_label` för varje label i templaten och i `extra_labels`.
   Kontrollera assignees, om några ska sättas, med `mcp__github__list_repository_collaborators`.
   Skriv resultatet till `repo-monitor/issue-work/meta.json`:
   `{"labels_existing": [...], "labels_missing": [...], "assignable": [... eller null], "milestones": null}`
5. **Utkast:** skriv svaren till `repo-monitor/issue-work/answers.json`. Nycklarna är fält-id (från
   `issue template`), eller fältens label, plus `title` om titeln ska anges. Kör:
   `python3 -m repo_monitor issue draft --template-file repo-monitor/issue-work/template.yml --answers repo-monitor/issue-work/answers.json --repo-meta repo-monitor/issue-work/meta.json`
   Slutkod 3 betyder att något saknas eller är fel. Fråga användaren och kör om.
6. **Visa utkastet** som verktyget skrev det och fråga **"Vill du att jag skapar denna issue?"** Vänta på svar.
7. **Efter uttryckligt ja:** `python3 -m repo_monitor issue payload <utkast-id>`. Anropa
   `mcp__github-issues__issue_write` med **exakt** de fälten och ändra ingenting.
8. **Svara kort:**
   - Länken till issuen.
   - Att GitHub Action nu skapar kandidatens repo och skickar inbjudan.
   - Att du kan svara på om kandidaten har committat något. Kandidatens repo följs nu (se
     `registered_repository` i `python3 -m repo_monitor issue list`, eller `registry find "<namn>"`).

   Om spärren inte fick med länken: `python3 -m repo_monitor issue record <utkast-id> --url <länk>`.
   Vid fel från GitHub: förklara felet enkelt och skapa inte issuen igen utan ett nytt godkännande.

## Om `mcp__github-issues__issue_write` saknas

Servern `github-issues` är inte ansluten. Använd **inte** något annat skrivverktyg. Förklara att
`GITHUB_ISSUES_TOKEN` och servern `github-issues` behöver konfigureras (`docs/skapa-issue.md`). Utkastet
är sparat och kan skapas senare.
