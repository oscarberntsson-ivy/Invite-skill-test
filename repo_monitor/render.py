"""Svenska rapporter i enkelt språk (Markdown)."""

from __future__ import annotations

from . import analysis as A
from .timeutil import LOCAL_TZ_LABEL, fmt_date, fmt_datetime

MAX_EVENTS = 15
MAX_MESSAGES_PER_PERSON = 5
MAX_FILES_PER_PERSON = 8

STATUS_EXPLANATION = {
    A.INAKTIVT: "Ingen kod har laddats upp av någon contributor ännu.",
    A.PABORJAT: "Minst en kodändring har laddats upp.",
    A.AKTIVT: "Flera personer har bidragit, eller arbete har skett vid flera tillfällen.",
    A.OKANT: "Kodaktiviteten kunde inte kontrolleras.",
    A.EJ_TILLGANGLIGT: "Agenten kunde inte läsa projektet på GitHub.",
    A.UNDER_GRANSKNING: "Det finns förslag på ändringar (pull requests) som väntar på granskning.",
    A.MERGAT: "Kod har godkänts och förts in i huvudprojektet.",
    A.INGA_PR: "Inga förslag på ändringar (pull requests) har skapats.",
}

GLOSSARY = [
    ("Commit", "en sparad ändring i koden, med ett kort meddelande om vad som ändrats."),
    ("Push", "när sparade ändringar laddas upp till GitHub."),
    ("Branch (gren)", "en separat arbetskopia av koden där man kan arbeta utan att påverka huvudprojektet."),
    ("Pull request", "ett förslag om att föra in ändringar från en gren till huvudprojektet. Andra kan granska förslaget först."),
    ("Merge", "när ett förslag godkänns och ändringarna förs in i huvudprojektet."),
]


def _plural(n, one, many):
    return f"{n} {one if n == 1 else many}"


def _people(n):
    return _plural(n, "person", "personer")


def _branch_text(branches, default_branch):
    if not branches:
        return ""
    names = []
    for b in branches:
        names.append("huvudgrenen" if b == default_branch else f"grenen ”{b}”")
    return " på " + " och ".join(names)


def _review_line(a) -> str:
    rs = a["review_status"]
    return " + ".join(rs)


def _header(a) -> list[str]:
    p = a["project"]
    lines = [f"## PROJEKT: {p['project_name']}", ""]
    lines.append(f"- **Repository:** [{p['full_name']}]({p['url']})")
    if p.get("person_name") or p.get("github_username"):
        who = p.get("person_name") or p["github_username"]
        if p.get("person_name") and p.get("github_username"):
            who += f" (GitHub: {p['github_username']})"
        lines.append(f"- **Person:** {who}")
    if p.get("invitation_issue"):
        ref = f"#{p['invitation_issue']}"
        if p.get("invitation_issue_url"):
            ref = f"[{ref}]({p['invitation_issue_url']})"
        when = f" den {fmt_date(p['invited_at'])}" if p.get("invited_at") else ""
        lines.append(f"- **Beställd via issue:** {ref}{when}")
    lines.append(f"- **Skapat:** {fmt_date(p['created_at']) if p['created_at'] else 'okänt (kunde inte hämtas)'}")
    lines.append(f"- **Kontrollerat:** {fmt_datetime(a['checked_at'])} ({LOCAL_TZ_LABEL})")
    lines.append("")
    return lines


def _unavailable(a) -> list[str]:
    lines = _header(a)
    lines.append(f"**STATUS: {A.EJ_TILLGANGLIGT}**")
    lines.append("")
    lines.append("Agenten kunde inte läsa det här projektet på GitHub. "
                 "**Det betyder inte att projektet är inaktivt** – vi vet helt enkelt inte.")
    err = a["access"].get("error")
    if err:
        lines.append("")
        lines.append(f"Felmeddelande från GitHub: `{err}`")
    lines += ["", "**Möjliga orsaker:**",
              *(["- Repositoryt har kanske inte skapats ännu – det beställdes via en issue, men "
                 "GitHub Action kan ha misslyckats eller inte körts."]
                if a["project"].get("invitation_issue") else []),
              "- Repositoryt har bytt namn, flyttats eller tagits bort.",
              "- Repositoryt är privat och GitHub-token saknar åtkomst till det.",
              "- Tillfälligt problem med anslutningen till GitHub (MCP).",
              "", "**Nästa steg:** Kontrollera repositoryts namn och att GitHub-token har "
              "läsbehörighet till det. Se docs/felsokning.md."]
    return lines


def _gaps(a) -> list[str]:
    lines = []
    if a.get("data_gaps") or a.get("errors"):
        lines += ["", "### ⚠️ Information som inte kunde hämtas", ""]
        for g in a.get("data_gaps") or []:
            lines.append(f"- {g.capitalize()} kunde inte hämtas. Uppgifter som bygger på detta "
                         "visas som *okänt* – det betyder inte att aktivitet saknas.")
        for e in a.get("errors") or []:
            lines.append(f"- {e['what']}: {e['message']}")
    return lines


def _fmt_count(value, one, many):
    return "okänt" if value is None else _plural(value, one, many)


def _status_block(a) -> list[str]:
    lines = []
    lines.append(f"**KODSTATUS: {a['code_status']}** – {STATUS_EXPLANATION[a['code_status']]}")
    lines.append("")
    rs = a["review_status"]
    lines.append(f"**GRANSKNING: {_review_line(a)}** – " + " ".join(STATUS_EXPLANATION[r] for r in rs))
    lines.append("")
    lines.append("### Aktivitet")
    lines.append("")
    lines.append(f"- **Antal kodändringar (commits):** {_fmt_count(a['commit_count'], 'commit', 'commits')}")
    if a.get("setup_commit_count"):
        lines.append(f"  - Utöver detta: {_plural(a['setup_commit_count'], 'automatisk startcommit', 'automatiska startcommits')} "
                     "från när projektet skapades (räknas inte som bidrag).")
    if a.get("merge_commit_count"):
        lines.append(f"  - Utöver detta: {_plural(a['merge_commit_count'], 'sammanslagning (merge-commit)', 'sammanslagningar (merge-commits)')}.")
    lines.append(f"- **Antal contributors:** {_fmt_count(a['contributor_count'], 'person', 'personer')}")
    last = a.get("last_activity")
    if last:
        lines.append(f"- **Senaste aktivitet:** {fmt_datetime(last['date'])} – {_event_text(last, a['default_branch'])}")
    elif a["code_status"] == A.OKANT:
        lines.append("- **Senaste aktivitet:** okänt")
    else:
        lines.append("- **Senaste aktivitet:** ingen aktivitet sedan projektet skapades")
    if a.get("last_push"):
        lines.append(f"- **Senaste uppladdning (push) till GitHub:** {fmt_datetime(a['last_push'])}")
    lines.append(f"- **Senaste contributor:** {a.get('last_contributor') or ('okänt' if a['commit_count'] is None else 'ingen ännu')}")
    if a.get("open_prs") is None:
        lines.append("- **Öppna pull requests:** okänt")
    else:
        lines.append(f"- **Öppna pull requests:** {len(a['open_prs'])}")
        lines.append(f"- **Mergade pull requests:** {len(a['merged_prs'])}")
    if a.get("branches") is not None:
        side = [b["name"] for b in a["side_branches"]]
        if side:
            lines.append(f"- **Grenar (branches) utöver huvudgrenen:** {', '.join(side)}")
        elif not a["branches"]:
            lines.append("- **Grenar (branches):** inga ännu (repositoryt är tomt)")
        else:
            lines.append("- **Grenar (branches):** bara huvudgrenen")
    return lines


def _meaning(a) -> list[str]:
    cs = a["code_status"]
    n = a.get("contributor_count") or 0
    parts = []
    if cs == A.INAKTIVT:
        parts.append("Projektet är skapat, men ingen kod har laddats upp till GitHub ännu. "
                     "Det betyder inte nödvändigtvis att ingen arbetar – arbete kan pågå på någons "
                     "dator utan att ha laddats upp.")
    elif cs == A.PABORJAT:
        parts.append(f"Projektet har börjat utvecklas. {_people(n).capitalize()} har bidragit med kod.")
    elif cs == A.AKTIVT:
        parts.append(f"Projektet utvecklas. {_people(n).capitalize()} har bidragit med kod.")
    elif cs == A.OKANT:
        parts.append("Vi kunde inte hämta information om kodändringar, så vi kan inte säga hur långt projektet har kommit.")

    if a.get("commit_count") and a.get("commits_on_default_branch") == 0 and a.get("branches") is not None:
        parts.append("All kod ligger än så länge på sidogrenar och har inte förts in i huvudprojektet.")
    open_prs = a.get("open_prs") or []
    if open_prs:
        parts.append(f"{_plural(len(open_prs), 'förslag', 'förslag')} på ändringar väntar på granskning.")
    if a.get("merged_prs"):
        parts.append(f"{_plural(len(a['merged_prs']), 'förslag har', 'förslag har')} godkänts och förts in i huvudprojektet.")
    if a.get("invited_inactive") and cs != A.OKANT:
        parts.append("Inbjudna som ännu inte bidragit med kod: " + ", ".join(a["invited_inactive"]) + ".")
    return ["", "### Vad betyder det?", "", " ".join(parts)]


def _next_steps(a) -> list[str]:
    steps = []
    open_prs = a.get("open_prs") or []
    if [g for g in a.get("data_gaps") or [] if g != "skapandedatum"]:
        steps.append("Kör kontrollen igen när anslutningen fungerar, så att all information kan hämtas.")
    if open_prs:
        steps.append("Koden behöver granskas innan den kan integreras i huvudprojektet.")
    if a["code_status"] == A.INAKTIVT:
        if a.get("invited_inactive"):
            steps.append("Om inget händer inom kort kan det vara bra att höra av sig till de inbjudna.")
        else:
            steps.append("Vänta på att någon börjar arbeta, eller hör av dig till de inbjudna.")
    side_with_code = [b["name"] for b in (a.get("side_branches") or []) if b["commits"]]
    unmerged_side = [b for b in side_with_code if not any(p.get("head") == b for p in (a.get("open_prs") or []) + (a.get("merged_prs") or []))]
    if unmerged_side and not open_prs:
        steps.append("Det finns kod på sidogrenar (" + ", ".join(unmerged_side) +
                     ") som ännu inte föreslagits för huvudprojektet via en pull request.")
    if not steps:
        steps.append("Inga åtgärder krävs just nu. Fortsätt följa projektet.")
    return ["", "### Nästa steg", ""] + [f"- {s}" for s in steps]


def _event_text(e, default_branch) -> str:
    t = e["type"]
    who = e.get("who") or "Någon"
    if t == A.EV_REPO_CREATED:
        return "Projektet (repositoryt) skapades."
    if t == A.EV_SETUP_COMMIT:
        return "Startfiler lades till automatiskt när projektet skapades."
    if t == A.EV_COMMIT:
        return (f"{who} sparade en kodändring (commit){_branch_text(e.get('branches'), default_branch)}. "
                f"Commit-meddelande: ”{e.get('message')}”")
    if t == A.EV_MERGE_COMMIT:
        return f"{who} slog ihop kod från en gren till en annan (merge-commit){_branch_text(e.get('branches'), default_branch)}."
    if t == A.EV_PUSH:
        return "Kod laddades upp (push) till GitHub."
    if t == A.EV_PR_OPENED:
        target = "huvudgrenen" if e.get("base") == default_branch else f"grenen ”{e.get('base')}”"
        return f"{who} skapade ett förslag på ändringar (pull request #{e['number']}: ”{e['title']}”) till {target}."
    if t == A.EV_PR_MERGED:
        by = f" av {e['who']}" if e.get("who") else ""
        return f"Förslaget pull request #{e['number']} (”{e['title']}”) godkändes och fördes in (mergades){by}."
    if t == A.EV_PR_CLOSED:
        return f"Förslaget pull request #{e['number']} (”{e['title']}”) stängdes utan att föras in."
    return t


def render_activity(a, limit=MAX_EVENTS) -> list[str]:
    lines = ["", "### Senaste händelser (nyast först)", ""]
    events = a.get("events") or []
    if not events:
        lines.append("- Inga händelser hittades.")
    for e in events[:limit]:
        when = fmt_datetime(e["date"]) if e.get("date") else "okänd tidpunkt"
        lines.append(f"- **{when}:** {_event_text(e, a['default_branch'])}")
    if len(events) > limit:
        lines.append(f"- … och {len(events) - limit} äldre händelser.")
    lines.append("")
    lines.append("*Tidpunkten för en commit är när ändringen sparades. Den kan ha laddats upp (pushats) senare.*")
    return lines


def render_contributors(a) -> list[str]:
    lines = ["", "### Vilka har bidragit och vad har de gjort?", ""]
    people = a.get("contributors")
    if people is None:
        return lines + ["Informationen om commits kunde inte hämtas, så contributors är okända."]
    if not people:
        lines.append("Ingen har bidragit med kod ännu.")
    for p in people:
        period = fmt_date(p["first_date"])
        if p["last_date"] and fmt_date(p["last_date"]) != period:
            period += f" – {fmt_date(p['last_date'])}"
        lines.append(f"#### {p['display']}")
        lines.append(f"- {_plural(p['commits'], 'kodändring', 'kodändringar')} ({period})")
        if p["branches"]:
            lines.append("- Har arbetat på: " + ", ".join(
                "huvudgrenen" if b == a["default_branch"] else f"grenen ”{b}”" for b in p["branches"]))
        if p["files"]:
            shown = p["files"][:MAX_FILES_PER_PERSON]
            more = len(p["files"]) - len(shown)
            lines.append("- Ändrade filer: " + ", ".join(f"`{f}`" for f in shown) +
                         (f" och {more} till" if more > 0 else ""))
        lines.append("- Commit-meddelanden (tekniska, nyast först):")
        for m in p["messages"][:MAX_MESSAGES_PER_PERSON]:
            lines.append(f"  - {fmt_date(m['date'])}: ”{m['message']}”")
        if len(p["messages"]) > MAX_MESSAGES_PER_PERSON:
            lines.append(f"  - … och {len(p['messages']) - MAX_MESSAGES_PER_PERSON} till")
        lines.append("")
    if a.get("invited_inactive"):
        lines.append("**Inbjudna som ännu inte bidragit med kod:** " + ", ".join(a["invited_inactive"]))
    prs = (a.get("open_prs") or []) + (a.get("merged_prs") or [])
    if prs:
        lines += ["", "**Pull requests per person:**"]
        for pr in prs:
            state = "väntar på granskning" if pr["state"] == "open" else "mergad"
            lines.append(f"- {pr.get('author') or 'okänd'}: #{pr['number']} ”{pr['title']}” ({state})")
    return lines


def render_candidate(a: dict) -> str:
    """Kort svar: har den inbjudna personen committat något?"""
    p = a["project"]
    user = p.get("github_username")
    who = p.get("person_name") or user or p["project_name"]
    if p.get("person_name") and user:
        who = f"{p['person_name']} ({user})"
    repo = p["full_name"]
    if a["code_status"] == A.EJ_TILLGANGLIGT:
        reason = " Det har kanske inte skapats ännu." if p.get("invitation_issue") else ""
        return (f"**Okänt** – repot {repo} kunde inte läsas.{reason} "
                f"({a['access'].get('error') or 'okänt fel'})\n")
    if a.get("contributors") is None:
        return f"**Okänt** – commits i {repo} kunde inte hämtas.\n"
    mine = [c for c in a["contributors"] if user and (c["login"] or "").lower() == user.lower()] \
        if user else a["contributors"]
    n = sum(c["commits"] for c in mine)
    last = max((c["last_date"] for c in mine if c["last_date"]), default=None)
    if n:
        line = f"**Ja** – {who} har gjort {n} {'commit' if n == 1 else 'commits'} i {repo}"
        line += f", senast {fmt_date(last)}." if last else "."
    else:
        line = f"**Nej** – {who} har inte committat något i {repo} ännu."
    if a.get("since_commits") is not None:
        new = [c for c in a["since_commits"]
               if not user or (c.get("author_login") or "").lower() == user.lower()]
        line += (f" Sedan {fmt_date(a['since'])}: "
                 + (f"{len(new)} {'commit' if len(new) == 1 else 'commits'}." if new else "inga commits."))
    return line + "\n"


def render(a: dict, view: str = "report") -> str:
    if view == "candidate":
        return render_candidate(a)
    if a["code_status"] == A.EJ_TILLGANGLIGT:
        return "\n".join(_unavailable(a)) + "\n"
    lines = _header(a)
    if view == "status":
        lines += _status_block(a) + _meaning(a) + _next_steps(a)
    elif view == "activity":
        lines += [f"**KODSTATUS: {a['code_status']}** · **GRANSKNING: {_review_line(a)}**"]
        lines += render_activity(a)
    elif view == "contributors":
        lines += [f"**Antal contributors:** {_fmt_count(a['contributor_count'], 'person', 'personer')}"]
        lines += render_contributors(a)
    else:  # report
        lines += _status_block(a) + _meaning(a) + _next_steps(a)
        lines += render_contributors(a)
        lines += render_activity(a)
        lines += ["", "### Ordlista", ""] + [f"- **{w}:** {d}" for w, d in GLOSSARY]
    lines += _gaps(a)
    return "\n".join(lines).rstrip() + "\n"


# --------------------------------------------------------------------------
# Översikt över flera repositories
# --------------------------------------------------------------------------

def render_overview(analyses: list[dict], checked_at) -> str:
    lines = ["## ÖVERSIKT: alla challenge-repositories", "",
             f"Kontrollerat: {fmt_datetime(checked_at)} ({LOCAL_TZ_LABEL})", ""]
    total = len(analyses)
    counts: dict[str, int] = {}
    for a in analyses:
        counts[a["code_status"]] = counts.get(a["code_status"], 0) + 1
    review = sum(1 for a in analyses if A.UNDER_GRANSKNING in a["review_status"])
    summary = [f"{_plural(total, 'projekt', 'projekt')} totalt"]
    for s in (A.AKTIVT, A.PABORJAT, A.INAKTIVT, A.OKANT, A.EJ_TILLGANGLIGT):
        if counts.get(s):
            summary.append(f"{counts[s]} {s}")
    if review:
        summary.append(f"{review} med pull requests som väntar på granskning")
    lines.append("**Sammanfattning:** " + ", ".join(summary) + ".")
    lines += ["", "| Projekt | Kodstatus | Granskning | Commits | Contributors | Öppna PR | Senaste aktivitet |",
              "|---|---|---|---|---|---|---|"]
    order = {A.AKTIVT: 0, A.PABORJAT: 1, A.INAKTIVT: 2, A.OKANT: 3, A.EJ_TILLGANGLIGT: 4}
    for a in sorted(analyses, key=lambda x: (order.get(x["code_status"], 9), x["project"]["project_name"].lower())):
        p = a["project"]
        if a["code_status"] == A.EJ_TILLGANGLIGT:
            lines.append(f"| {p['project_name']} | {A.EJ_TILLGANGLIGT} | – | – | – | – | kunde inte hämtas |")
            continue
        last = a.get("last_activity")
        lines.append("| {} | {} | {} | {} | {} | {} | {} |".format(
            p["project_name"], a["code_status"], _review_line(a),
            "?" if a["commit_count"] is None else a["commit_count"],
            "?" if a["contributor_count"] is None else a["contributor_count"],
            "?" if a.get("open_prs") is None else len(a["open_prs"]),
            fmt_date(last["date"]) if last else "–",
        ))

    inactive = [a["project"]["project_name"] for a in analyses if a["code_status"] == A.INAKTIVT]
    lines += ["", "### Inaktiva projekt", ""]
    lines.append("- " + "\n- ".join(inactive) if inactive else "- Inga – alla kontrollerade projekt har kodaktivitet.")
    unavailable = [a for a in analyses if a["code_status"] == A.EJ_TILLGANGLIGT]
    if unavailable:
        lines += ["", "### Kunde inte kontrolleras", ""]
        for a in unavailable:
            hint = (" – repot har kanske inte skapats ännu (inbjudan finns)"
                    if a["project"].get("invitation_issue") else "")
            lines.append(f"- {a['project']['full_name']}: {a['access'].get('error') or 'okänt fel'}{hint} "
                         "(betyder inte att projektet är inaktivt)")
    partial = [a for a in analyses if a.get("data_gaps") and a["code_status"] != A.EJ_TILLGANGLIGT]
    if partial:
        lines += ["", "### Ofullständig information", ""]
        for a in partial:
            lines.append(f"- {a['project']['full_name']}: kunde inte hämta {', '.join(a['data_gaps'])}")
    return "\n".join(lines).rstrip() + "\n"
