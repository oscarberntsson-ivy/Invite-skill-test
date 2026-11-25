# Bjud in en kandidat

Flödet:
1. Användaren ber om att bjuda in en kandidat.
2. Du ställer templatens frågor.
3. Användaren svarar.
4. Du visar ett utkast.
5. Efter ett uttryckligt ja skapar du issuen.
6. GitHub Action skapar då kandidatens repo och bjuder in kandidaten.

## 1. Läs templaten

Hämta templaten med `get_file_contents` från inbjudnings-repot och sökvägen i konfigurationen.
- Får du 404 eller 403: förklara att templaten inte kunde läsas och avsluta.
- Gissa aldrig, och använd aldrig en annan template.

Templaten är oftast ett **YAML-formulär** (`.yml`). Ur den behöver du:
- `title`: förifylld titel, ofta ett prefix som `"[Kandidat]: "`.
- `labels`: ska följa med issuen. GitHub Action kan bero på dem.
- `body`: fälten. Varje fält har en `type`:
  - `markdown`: bara information. Ingen fråga och inget i issuen.
  - `input` och `textarea`: text. `attributes.label` är frågan.
  - `dropdown`: val bland `attributes.options` (flera val bara om `multiple: true`).
  - `checkboxes`: rutor i `attributes.options[].label`. En ruta med `required: true` måste kryssas.
  - `validations.required: true` betyder att fältet är obligatoriskt.

Är templaten i stället **Markdown** (`.md`): front matter (`title`, `labels`) överst och rubriker i texten.

## 2. Ställ frågorna

Visa alla frågor i **ett** meddelande som en numrerad lista. Ta med fältets label, om det är
obligatoriskt, beskrivningen (`attributes.description`) och de tillåtna valen. Har användaren redan
gett några svar (till exempel namnet): skriv vad du redan har, och fråga bara efter resten. **Vänta
på svar.** Fyll aldrig i obligatoriska uppgifter själv.

## 3. Kontrollera mot GitHub

- **Labels:** kör `get_label` för varje label i templaten. Saknas någon: berätta det och skapa
  ingen issue, eftersom GitHub Action troligen behöver den.
- **Tidigare inbjudningar:** kör `list_issues` i inbjudnings-repot med både öppna och stängda issues.
  Leta efter samma GitHub-användarnamn (se "Läsa en inbjudan" i [uppfoljning.md](uppfoljning.md)).
  - Finns en **öppen** inbjudan: berätta det, med länk, och skapa ingen ny.
  - Finns en **stängd**: nämn det och fråga om en ny inbjudan ändå ska skapas.

## 4. Bygg issuen exakt som GitHubs formulär gör

**Titel:** templatens `title` följt av användarens svar, till exempel `[Kandidat]: Anna Andersson`.
Föreslå kandidatens namn om användaren inte har angett någon titel.

**Beskrivning (body),** för YAML-formulär. Gå igenom fälten i templatens ordning och hoppa över
`markdown`. Skriv varje fält som:

```
### <label>

<svar>
```

Separera fälten med en tom rad, och följ dessa regler:
- Tomt valfritt fält: skriv `_No response_`.
- Förifyllt värde (`attributes.value`) utan nytt svar: använd det förifyllda värdet.
- Dropdown med flera val: separera valen med `, `.
- Checkboxes: en rad per ruta, `- [X] <label>` om den är kryssad och `- [ ] <label>` om den inte är det.
- `render`-fält: lägg svaret i ett kodblock med det språket.

För Markdown-templates: behåll rubrikerna i samma ordning och skriv svaren under dem.

**Labels:** templatens labels.

## 5. Visa utkastet och be om godkännande

```
**Ny GitHub-issue (utkast)**
Repository: <inbjudnings-repo>
Template: <templatens name>
Titel: <titel>
Labels: <labels>

Beskrivning:
<body>

Vill du att jag skapar denna issue?
```

Skapa **bara** om användaren svarar uttryckligen ja ("ja", "skapa", "godkänt"). Ändras något: visa
ett nytt utkast och fråga igen.

## 6. Skapa issuen

Anropa `issue_write` med `method: "create"` och följande fält:
- `owner` och `repo` för inbjudnings-repot,
- `title`, `body` och `labels` exakt som i utkastet.

Svara sedan kort:
- Länken till issuen.
- Att GitHub Action nu skapar kandidatens repo, `ivy-engineering-challenge-<användarnamn>`.
- Att användaren senare kan fråga om kandidaten har committat något.

Svarar GitHub med fel (till exempel 403, saknad behörighet): förklara enkelt. Försök inte igen
utan ett nytt ja.
