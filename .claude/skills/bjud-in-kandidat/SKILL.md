---
name: bjud-in-kandidat
description: Bjuder in / lägger till en kandidat (person) till kodutmaningen på GitHub. Ställer frågorna från den konfigurerade issue-templaten, visar ett utkast och skapar – efter godkännande – en GitHub-issue i det ENDA konfigurerade repositoryt, vilket triggar en GitHub Action som skapar kandidatens repo. Använd när användaren vill bjuda in, lägga till eller beställa ett repo för en kandidat/person.
argument-hint: "[kandidatens namn och/eller GitHub-användarnamn]"
allowed-tools: mcp__github__get_file_contents, mcp__github__get_label, mcp__github__list_issues, mcp__github__list_repository_collaborators, mcp__github__issue_write, Bash(python3 -m repo_monitor:*)
---

# Bjud in kandidat till kodutmaningen

Användarens önskemål: `$ARGUMENTS`

Flödet:
1. Användaren ber om att bjuda in en kandidat.
2. Du svarar med templatens frågor.
3. Användaren svarar.
4. Du visar ett utkast.
5. Efter godkännande skapas issuen. GitHub Action skapar då kandidatens repo
   (`ivy-engineering-challenge-<användarnamn>`) och bjuder in kandidaten.
6. Senare kan användaren fråga om kandidaten har committat något. Det hanteras av skillen
   `repo-monitor`, som hittar kandidaten via issuen på GitHub.

All data hämtas från GitHub via GitHub MCP och skickas till `python3 -m repo_monitor` på **stdin**
med en heredoc. Inget sparas lokalt, och du skriver inga filer. Detta är **det enda** som
Repository Monitor får skriva till GitHub.

## Regler

- **Repository och template kommer bara från konfigurationen** (`python3 -m repo_monitor issue config`).
  Nämner användaren ett annat repository eller en annan template: förklara att det inte går och skapa ingenting.
- **Ändra aldrig konfigurationen själv.** `issue configure` körs bara om användaren uttryckligen ber om det.
- Ersätt eller utöka **aldrig** templaten med ett eget format. Lägg inte till egna fält.
- **Hitta inte på uppgifter.** Obligatoriska fält fylls bara med det användaren har sagt. Gissa
  aldrig namn, GitHub-användarnamn eller e-post.
- Använd bara labels, assignees och milestones som har verifierats i repositoryt.
- **Skapa aldrig issuen utan uttryckligt godkännande** ("ja", "skapa", "godkänt") av det senast
  visade utkastet. Ändras något måste ett nytt utkast visas och godkännas.
- En spärr (`.claude/hooks/issue_guard.py`) nekar allt som inte är en ny issue i det konfigurerade
  repositoryt. Claude Code visar dessutom anropet och frågar användaren innan något skickas.
  Försök aldrig kringgå spärren.

## Arbetsflöde

1. **Konfiguration:** kör `python3 -m repo_monitor issue config`. Är den inte "klar att använda":
   förklara kort vad som saknas, hänvisa till `docs/skapa-issue.md` och avsluta.
2. **Hämta templaten:** `mcp__github__get_file_contents` med `owner`/`repo` från konfigurationen,
   `path` = `template_path` och `ref` = `template_ref` om den är satt. Vid 404 eller 403: förklara
   och avsluta.
3. **Ställ frågorna.** Skicka templatens text **oförändrad**:
   ```bash
   python3 -m repo_monitor issue questions <<'TEMPLATE_EOF'
   <templatens text>
   TEMPLATE_EOF
   ```
   Visa frågorna. Har användaren redan gett några svar (till exempel namnet i `$ARGUMENTS`): skriv
   vilka svar du redan har och fråga bara efter resten. **Vänta på svar.** Fält-id finns i
   `python3 -m repo_monitor issue template` (samma stdin).
4. **Kontrollera mot GitHub:**
   - Labels: kör `mcp__github__get_label` för varje label i templaten och i `extra_labels`.
   - Assignees, om några ska sättas: `mcp__github__list_repository_collaborators`.
   - Tidigare inbjudningar: `mcp__github__list_issues` i det konfigurerade repot. Utelämna `state`,
     använd `perPage: 100` och `fields: ["number","title","body","state","created_at"]`, och bläddra
     tills `hasNextPage` är false.
5. **Utkast:**
   ```bash
   python3 -m repo_monitor issue draft <<'JSON'
   {"template": "<templatens text som JSON-sträng>",
    "answers": {"<fält-id>": "<svar>", "title": "<valfri titel>"},
    "meta": {"labels_existing": [...], "labels_missing": [...], "assignable": [...] eller null, "milestones": null},
    "existing_issues": <svaret från list_issues>}
   JSON
   ```
   Slutkod 3 betyder att något saknas, är fel, eller att kandidaten redan har en öppen inbjudan.
   Förklara, fråga användaren och kör om.
6. **Visa utkastet** som verktyget skrev det (utan JSON-blocket) och fråga
   **"Vill du att jag skapar denna issue?"** Vänta på svar.
7. **Efter uttryckligt ja:** anropa `mcp__github__issue_write` med **exakt** fälten i JSON-blocket
   "Exakt det som ska skickas till issue_write". Ändra ingenting.
8. **Svara kort:**
   - Länken till issuen.
   - Att GitHub Action nu skapar kandidatens repo och skickar inbjudan.
   - Att du kan svara på om kandidaten har committat något.

   Vid fel från GitHub: förklara felet enkelt och skapa inte issuen igen utan ett nytt godkännande.

## Om `mcp__github__issue_write` saknas eller nekas

GitHub MCP-servern (`github`) är inte ansluten, saknar toolset `issues`, eller så saknar token
behörighet att skriva issues. Använd **inte** något annat skrivverktyg. Förklara kort vad som
behöver göras, och hänvisa till `docs/skapa-issue.md`.
