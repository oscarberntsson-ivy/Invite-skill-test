# Felsökning

| Symptom | Trolig orsak | Åtgärd |
|---|---|---|
| "Skillen är inte konfigurerad ännu" | `konfiguration.md` innehåller fortfarande `ÄGARE/REPO` eller `SÖKVÄG` | Fyll i den, och ladda upp skillen igen om du använder claude.ai. |
| Claude säger att GitHub-kopplingen inte är ansluten | Kopplingen saknas eller är avslagen | claude.ai: kontrollera under *Connectors*. Claude Code: kör `/mcp`. |
| `401 Unauthorized` | Token är ogiltig eller har gått ut | Skapa en ny token (se [installation.md](installation.md)). |
| `403` när inbjudan skapas | Token saknar *Issues: Read and write* på inbjudnings-repot | Uppdatera tokenens behörigheter. |
| `403` eller `404` när ett repo läses | Token saknar åtkomst till repot, eller så finns repot inte | Ge token åtkomst. Har kandidaten nyss bjudits in har GitHub Action kanske inte skapat repot än. |
| "Okänt – repot kunde inte läsas" | Repot finns inte (än), eller saknar åtkomst | Kontrollera i GitHub att GitHub Action har körts för inbjudan. |
| Kandidaten hittas inte | Inbjudnings-issuen saknas, eller fältnamnen i `konfiguration.md` stämmer inte med templaten | Jämför fältens rubriker i en inbjudnings-issue med `konfiguration.md`. |
| "Labeln … finns inte" | Templatens label saknas i inbjudnings-repot | Skapa labeln i repot. GitHub Action kan behöva den. |
| GitHub Action startade inte | Workflowen lyssnar inte på nya issues, eller villkoren uppfylls inte | Kontrollera workflowen (`on: issues: types: [opened]`) och eventuella villkor på label, titel eller författare. |

Inget sparas lokalt, så det finns ingen cache eller historik att rensa.
