# Följ upp kandidater

## Läsa en inbjudan

Inbjudningarna är issues i inbjudnings-repot. De skapades med templaten, så beskrivningen ser ut så här:

```
### Namn

Anna Andersson

### GitHub-användarnamn

anna-a
```

Namnet och användarnamnet står under rubrikerna från konfigurationen. Tvätta användarnamnet:
- ta bort `@`, mellanslag och en eventuell `https://github.com/`,
- ta bara första raden.

Finns flera issues för samma användarnamn gäller den senaste.

## Hitta kandidaten

1. Kör `list_issues` i inbjudnings-repot, med både öppna och stängda issues och `perPage: 100`.
   Bläddra tills alla är hämtade.
2. Matcha användarens fråga mot namn och användarnamn. Bry dig inte om versaler, accenter
   (Åsa = Asa) eller `@`.
   - Flera träffar: fråga vem som avses.
   - Ingen träff: säg det, och nämn vilka kandidater som finns.
3. Kandidatens repo är `<organisation>/ivy-engineering-challenge-<användarnamn>`, med
   organisationen från konfigurationen.

## Har kandidaten committat något?

1. Kör `list_branches` på kandidatens repo.
   - **404:** prova stavningen `challange`. Ger även den 404, svara:
     **"Okänt – repot `<repo>` kunde inte läsas. Det har kanske inte skapats ännu."**
   - **409 "Git Repository is empty", eller inga branches:** svara att det inte finns några commits.
2. Kör `list_commits` för varje branch (högst 10), med följande parametrar:
   - `sha: <branch>`
   - `author: <användarnamn>`
   - `perPage: 100`
   - `since: <datum>`, om användaren frågar om en period ("sedan i måndags"). Räkna ut datumet
     från dagens datum.
3. Räkna **unika** commits (samma SHA kan finnas på flera branches) där `author.login` är kandidatens
   användarnamn. Commits från andra, till exempel en bot som skapade repot, räknas inte.
4. Svara **kort**, med bara en av följande rader:
   - **"Ja – Anna Andersson (anna-a) har gjort 3 commits i `<repo>`, senast 24 november 2026."**
   - **"Nej – Anna Andersson (anna-a) har inte committat något i `<repo>` ännu."**
   - Med period: lägg till **"Sedan 20 november 2026: 1 commit."** (eller "inga commits").

   Förklara inte vad som har gjorts, om användaren inte ber om det. Ber användaren om det:
   sammanfatta commit-meddelandena på enkel svenska och gissa inte.

## Översikt över alla kandidater

Hitta alla kandidater enligt ovan. Gör kontrollen ovan för var och en, utan `author` om du vill se
alla bidrag. Hämta också öppna pull requests (`list_pull_requests`, `state: "open"`). Visa en tabell:

| Kandidat | Repo | Status | Commits | Senaste commit | Öppna PR |
|---|---|---|---|---|---|

Status:
- **INAKTIVT:** inga commits från kandidaten.
- **PÅBÖRJAT:** commits under en dag.
- **AKTIVT:** commits under minst två olika dagar.
- **EJ SKAPAT/OKÄNT:** repot kunde inte läsas.

Lista sedan kort de inaktiva kandidaterna, och de inbjudningar där repot saknas.
