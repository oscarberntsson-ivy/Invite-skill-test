# Konfiguration

Fyll i detta en gång, innan skillen används eller laddas upp. Agenten får inte ändra filen.

| Inställning | Värde |
|---|---|
| Inbjudnings-repo (där issues skapas) | `ÄGARE/REPO` |
| Issue-template i inbjudnings-repot | `SÖKVÄG` (t.ex. `.github/ISSUE_TEMPLATE/bjud-in-kandidat.yml`) |
| Organisation där kandidaternas repos skapas | `IvyTechSE` |
| Namn på kandidatens repo | `ivy-engineering-challenge-<github-användarnamn>` |
| Fält i templaten med kandidatens namn | `Namn` (även `Name`, `Fullständigt namn` godtas) |
| Fält i templaten med kandidatens GitHub-användarnamn | `GitHub-användarnamn` (även `GitHub username`, `Användarnamn` godtas) |
| Konton vars commits inte räknas som kandidatens (t.ex. en bot) | *(inga)* |

Repo-namnet stavas ibland `challange`. Hittas inte `ivy-engineering-challenge-<användarnamn>`,
pröva även `ivy-engineering-challange-<användarnamn>`.
