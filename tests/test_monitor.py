"""Tester för monitoreringen med mockad GitHub-data.

Kör: python3 -m unittest discover -s tests -v
"""

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import factories as F  # noqa: E402
from repo_monitor import analysis as A  # noqa: E402
from repo_monitor import render, storage  # noqa: E402
from repo_monitor.cli import main  # noqa: E402
from repo_monitor.snapshot import normalize  # noqa: E402
from repo_monitor.timeutil import fmt_date, parse_iso  # noqa: E402

NOW = parse_iso("2026-11-24T12:00:00Z")


def run(raw, automation=("repo-bot",), since=None, person=None):
    if person:
        raw = {**raw, "person": person}
    return A.analyze(normalize(raw), list(automation), NOW, since)


def cli(*argv, stdin=None):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err), \
            mock.patch("sys.stdin", io.StringIO(stdin if stdin is not None else "")):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


class TempHome(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.home = Path(self._tmp.name)
        os.environ["REPO_MONITOR_HOME"] = str(self.home)

    def tearDown(self):
        os.environ.pop("REPO_MONITOR_HOME", None)
        self._tmp.cleanup()


# ---------------------------------------------------------------------------
# 1. Repository utan commits
# ---------------------------------------------------------------------------
class TestNoCommits(unittest.TestCase):
    def test_empty_repository_is_inactive(self):
        a = run(F.snapshot(F.repo(), {"main": []}))
        self.assertEqual(a["code_status"], A.INAKTIVT)
        self.assertEqual(a["commit_count"], 0)
        self.assertEqual(a["contributor_count"], 0)
        self.assertIsNone(a["last_activity"])
        self.assertEqual(a["review_status"], [A.INGA_PR])

    def test_real_empty_repository_from_mcp(self):
        raw = {"repo": {"owner": "o", "name": "tomt", "created_at": None}, "branches": [],
               "commits_by_branch": {}, "pull_requests": []}
        a = run(raw)
        self.assertEqual(a["code_status"], A.INAKTIVT)
        md = render.render(a, "status")
        self.assertIn("inga ännu (repositoryt är tomt)", md)
        self.assertIn("Skapandedatum kunde inte hämtas", md)
        self.assertNotIn("Kör kontrollen igen", md)

    def test_setup_commit_from_automation_is_not_a_contribution(self):
        a = run(F.snapshot(F.repo(), {"main": [F.setup_commit()]}))
        self.assertEqual(a["code_status"], A.INAKTIVT)
        self.assertEqual(a["setup_commit_count"], 1)
        self.assertEqual(a["commit_count"], 0)

    def test_initial_commit_right_after_creation_is_setup_even_without_bot(self):
        c = F.commit("oscar", "2026-11-01T09:01:00Z", "Initial commit")
        a = run(F.snapshot(F.repo(), {"main": [c]}), automation=())
        self.assertEqual(a["code_status"], A.INAKTIVT)

    def test_report_does_not_claim_nobody_works(self):
        a = run(F.snapshot(F.repo(), {"main": []}), person={"name": "Anna", "username": "anna"})
        md = render.render(a, "status")
        self.assertIn("KODSTATUS: INAKTIVT", md)
        self.assertIn("inte nödvändigtvis att ingen arbetar", md)
        self.assertEqual(a["invited_inactive"], ["anna"])


# ---------------------------------------------------------------------------
# 2. Repository med en commit
# ---------------------------------------------------------------------------
class TestOneCommit(unittest.TestCase):
    def test_single_commit_is_started(self):
        c = F.commit("anna", "2026-11-20T14:05:00Z", "Add login page", name="Anna Andersson")
        a = run(F.snapshot(F.repo(pushed_at="2026-11-20T14:06:00Z"), {"main": [c, F.setup_commit()]}))
        self.assertEqual(a["code_status"], A.PABORJAT)
        self.assertEqual(a["commit_count"], 1)
        self.assertEqual(a["last_contributor"], "Anna Andersson (anna)")
        self.assertEqual(a["last_push"], "2026-11-20T14:06:00Z")
        md = render.render(a, "report")
        self.assertIn("KODSTATUS: PÅBÖRJAT", md)
        self.assertIn("Add login page", md)
        self.assertIn("20 november 2026", md)
        self.assertNotIn("förra kontrollen", md)

    def test_events_are_kept_separate(self):
        c = F.commit("anna", "2026-11-20T14:05:00Z")
        a = run(F.snapshot(F.repo(pushed_at="2026-11-20T14:06:00Z"), {"main": [c, F.setup_commit()]}))
        types = {e["type"] for e in a["events"]}
        self.assertEqual(types, {A.EV_REPO_CREATED, A.EV_SETUP_COMMIT, A.EV_COMMIT, A.EV_PUSH})


# ---------------------------------------------------------------------------
# 3. Repository med flera contributors
# ---------------------------------------------------------------------------
class TestMultipleContributors(unittest.TestCase):
    def test_two_contributors_is_active(self):
        commits = [
            F.commit("erik", "2026-11-21T10:00:00Z", "Add authentication middleware", files=["src/auth.js"]),
            F.commit("anna", "2026-11-20T10:00:00Z", "Create landing page"),
            F.commit("anna", "2026-11-20T11:00:00Z", "Fix typo"),
        ]
        a = run(F.snapshot(F.repo(), {"main": commits}))
        self.assertEqual(a["code_status"], A.AKTIVT)
        self.assertEqual(a["contributor_count"], 2)
        anna = next(p for p in a["contributors"] if p["login"] == "anna")
        self.assertEqual(anna["commits"], 2)
        md = render.render(a, "contributors")
        self.assertIn("#### Anna", md)
        self.assertIn("`src/auth.js`", md)

    def test_one_person_on_several_days_is_active(self):
        commits = [F.commit("anna", "2026-11-20T10:00:00Z"), F.commit("anna", "2026-11-22T10:00:00Z")]
        self.assertEqual(run(F.snapshot(F.repo(), {"main": commits}))["code_status"], A.AKTIVT)

    def test_one_person_one_day_is_started(self):
        commits = [F.commit("anna", "2026-11-20T10:00:00Z"), F.commit("anna", "2026-11-20T12:00:00Z")]
        self.assertEqual(run(F.snapshot(F.repo(), {"main": commits}))["code_status"], A.PABORJAT)

    def test_person_name_is_used_for_invited_candidate(self):
        c = F.commit("anna-a", "2026-11-20T10:00:00Z", name="anna-a")
        a = run(F.snapshot(F.repo(), {"main": [c]}),
                person={"name": "Anna Andersson", "username": "anna-a", "issue_number": 3,
                        "issue_url": "https://github.com/o/r/issues/3"})
        self.assertEqual(a["last_contributor"], "Anna Andersson (anna-a)")
        md = render.render(a, "report")
        self.assertIn("**Person:** Anna Andersson (GitHub: anna-a)", md)
        self.assertIn("Beställd via issue:** [#3]", md)


# ---------------------------------------------------------------------------
# 4. Repository med flera branches
# ---------------------------------------------------------------------------
class TestMultipleBranches(unittest.TestCase):
    def test_commits_are_deduplicated_across_branches(self):
        base = F.setup_commit()
        shared = F.commit("anna", "2026-11-20T10:00:00Z", "Shared work")
        feature_only = F.commit("anna", "2026-11-20T11:00:00Z", "Feature work")
        a = run(F.snapshot(F.repo(), {"main": [base], "feature/login": [feature_only, shared, base],
                                      "dev": [shared, base]}))
        self.assertEqual(a["commit_count"], 2)
        self.assertEqual(a["commits_on_default_branch"], 0)
        self.assertEqual({b["name"]: b["commits"] for b in a["side_branches"]},
                         {"feature/login": 2, "dev": 1})
        self.assertIn("sidogrenar", render.render(a, "status"))


# ---------------------------------------------------------------------------
# 5. & 6. Öppna och mergade pull requests
# ---------------------------------------------------------------------------
class TestPullRequests(unittest.TestCase):
    def test_open_pr_gives_under_review(self):
        c = F.commit("anna", "2026-11-20T10:00:00Z")
        a = run(F.snapshot(F.repo(), {"main": [F.setup_commit()], "feature": [c]},
                           prs=[F.pr(1, "Inloggning", "anna")]))
        self.assertEqual(a["code_status"], A.PABORJAT)
        self.assertEqual(a["review_status"], [A.UNDER_GRANSKNING])
        self.assertIn("Koden behöver granskas", render.render(a, "status"))

    def test_merged_and_closed_pr(self):
        c = F.commit("anna", "2026-11-20T10:00:00Z")
        merge = F.commit("oscar", "2026-11-21T10:00:00Z", "Merge pull request #1", parents=2)
        a = run(F.snapshot(F.repo(), {"main": [merge, c, F.setup_commit()]}, prs=[
            F.pr(1, "Inloggning", "anna", merged_at="2026-11-21T10:00:00Z"),
            F.pr(2, "Avbruten idé", "erik", closed_at="2026-11-21T11:00:00Z")]))
        self.assertEqual(a["review_status"], [A.MERGAT])
        self.assertEqual(a["commit_count"], 1)
        self.assertEqual(a["merge_commit_count"], 1)
        md = render.render(a, "report")
        self.assertIn("GRANSKNING: MERGAT", md)
        self.assertIn("stängdes utan att föras in", md)

    def test_open_and_merged_can_overlap(self):
        a = run(F.snapshot(F.repo(), {"main": []}, prs=[
            F.pr(1, "A", "anna", merged_at="2026-11-21T10:00:00Z"), F.pr(2, "B", "anna")]))
        self.assertEqual(a["review_status"], [A.UNDER_GRANSKNING, A.MERGAT])


# ---------------------------------------------------------------------------
# 7. Aktivitet sedan ett datum (ersätter sparad historik)
# ---------------------------------------------------------------------------
class TestSince(unittest.TestCase):
    PERSON = {"name": "Anna Andersson", "username": "anna-a"}

    def snap(self):
        return F.snapshot(F.repo(), {"main": [
            F.commit("anna-a", "2026-11-23T10:00:00Z"), F.commit("anna-a", "2026-11-18T10:00:00Z"),
            F.commit("erik", "2026-11-23T11:00:00Z")]})

    def test_candidate_since_date(self):
        a = run(self.snap(), since="2026-11-20", person=self.PERSON)
        md = render.render(a, "candidate")
        self.assertIn("**Ja** – Anna Andersson (anna-a) har gjort 2 commits", md)
        self.assertIn("Sedan 20 november 2026: 1 commit.", md)

    def test_no_activity_since_date(self):
        a = run(self.snap(), since="2026-11-24", person=self.PERSON)
        self.assertIn("Sedan 24 november 2026: inga commits.", render.render(a, "candidate"))

    def test_candidate_without_since_has_no_comparison(self):
        md = render.render(run(self.snap(), person=self.PERSON), "candidate")
        self.assertNotIn("Sedan", md)
        self.assertNotIn("förra kontrollen", md)

    def test_candidate_no_commits(self):
        a = run(F.snapshot(F.repo(), {"main": [F.setup_commit()]}), person=self.PERSON)
        self.assertIn("**Nej** – Anna Andersson (anna-a) har inte committat något", render.render(a, "candidate"))


# ---------------------------------------------------------------------------
# 8. Repository som inte är tillgängligt / delvis saknad data
# ---------------------------------------------------------------------------
class TestInaccessible(unittest.TestCase):
    def test_inaccessible_is_not_inactive(self):
        a = run(F.inaccessible())
        self.assertEqual(a["code_status"], A.EJ_TILLGANGLIGT)
        md = render.render(a, "report")
        self.assertIn("betyder inte att projektet är inaktivt", md)
        self.assertIn("404 Not Found", md)

    def test_invited_but_repo_missing(self):
        a = run(F.inaccessible("ivy-engineering-challenge-anna"),
                person={"name": "Anna", "username": "anna", "issue_number": 5})
        self.assertIn("kanske inte skapats ännu", render.render(a, "report"))
        self.assertIn("**Okänt**", render.render(a, "candidate"))

    def test_partial_failure_commits_unknown(self):
        raw = F.snapshot(F.repo(), {"main": []})
        del raw["commits_by_branch"]
        raw["errors"] = [{"what": "commits", "message": "timeout"}]
        a = run(raw)
        self.assertEqual(a["code_status"], A.OKANT)
        md = render.render(a, "status")
        self.assertIn("Commits kunde inte hämtas", md)
        self.assertIn("timeout", md)
        self.assertIn("**Okänt**", render.render(a, "candidate"))


# ---------------------------------------------------------------------------
# 9. Flera repositories med olika aktivitetsnivåer (CLI, stdin, inget sparas)
# ---------------------------------------------------------------------------
class TestCli(TempHome):
    def test_overview_from_stdin(self):
        snaps = [
            {**F.snapshot(F.repo("ivy-engineering-challenge-tomt"), {"main": [F.setup_commit()]}),
             "person": {"name": "Tomas Tom", "username": "tomt"}},
            F.snapshot(F.repo("aktivt"), {"main": [F.commit("anna", "2026-11-20T10:00:00Z"),
                                                   F.commit("erik", "2026-11-21T10:00:00Z")]},
                       prs=[F.pr(3, "Ny funktion", "erik")]),
            {**F.inaccessible("ivy-engineering-challenge-asa"), "person": {"name": "Åsa", "username": "asa",
                                                                           "issue_number": 9}},
        ]
        code, out, err = cli("overview", "--now", "2026-11-24T12:00:00Z", stdin=json.dumps(snaps))
        self.assertEqual(code, 0, err)
        self.assertIn("3 projekt totalt", out)
        self.assertIn("| Tomas Tom | INAKTIVT |", out)
        self.assertIn("| aktivt | AKTIVT | UNDER GRANSKNING |", out)
        self.assertIn("repot har kanske inte skapats ännu", out)
        self.assertNotIn("förra kontrollen", out)
        self.assertEqual(sorted(p.name for p in self.home.iterdir()), [])  # inget sparas

    def test_analyze_stdin_and_file_and_json(self):
        snap = json.dumps(F.snapshot(F.repo(), {"main": [F.commit("anna", "2026-11-20T10:00:00Z")]}))
        code, out, _ = cli("analyze", "--view", "status", stdin=snap)
        self.assertEqual(code, 0)
        self.assertIn("KODSTATUS: PÅBÖRJAT", out)
        f = self.home / "s.json"
        f.write_text(snap, encoding="utf-8")
        code, out, _ = cli("analyze", str(f), "--format", "json")
        self.assertEqual(json.loads(out)["code_status"], A.PABORJAT)
        f.unlink()
        self.assertEqual(list(self.home.iterdir()), [])

    def test_errors(self):
        code, _, err = cli("analyze", stdin="")
        self.assertEqual(code, 2)
        self.assertIn("saknas", err)
        code, _, err = cli("analyze", stdin="{inte json")
        self.assertEqual(code, 2)
        self.assertIn("inte giltig JSON", err)
        code, _, err = cli("analyze", str(self.home / "saknas.json"))
        self.assertIn("finns inte", err)
        code, _, err = cli("analyze", "--since", "igår", stdin=json.dumps(F.snapshot(F.repo())))
        self.assertIn("Ogiltigt datum", err)
        code, _, err = cli("overview", stdin='{"x": 1}')
        self.assertEqual(code, 2)

    def test_automation_accounts_from_config(self):
        cli("discover", "configure", "--automation-accounts", "min-bot")
        snap = json.dumps(F.snapshot(F.repo(), {"main": [F.commit("min-bot", "2026-11-20T10:00:00Z")]}))
        code, out, _ = cli("analyze", "--format", "json", stdin=snap)
        self.assertEqual(json.loads(out)["code_status"], A.INAKTIVT)


# ---------------------------------------------------------------------------
class TestNormalization(unittest.TestCase):
    def test_simplified_format(self):
        raw = {"repo": {"owner": "o", "name": "r", "created_at": F.CREATED},
               "commits": [{"sha": "a" * 40, "author": "anna", "date": "2026-11-20T10:00:00Z",
                            "message": "Hej\n\nlång text", "branches": ["main"], "files": ["x.py"]}],
               "branches": ["main"],
               "pull_requests": [{"number": 1, "title": "t", "state": "OPEN", "author": "anna"}]}
        s = normalize(raw)
        self.assertEqual(s["commits"][0]["author_login"], "anna")
        self.assertEqual(s["pull_requests"][0]["state"], "open")

    def test_missing_sections_mean_unknown_not_empty(self):
        s = normalize({"repo": {"owner": "o", "name": "r"}})
        self.assertIsNone(s["commits"])
        self.assertIsNone(s["pull_requests"])

    def test_missing_repo_name_is_a_clear_error(self):
        with self.assertRaises(storage.MonitorError):
            normalize({"commits": []})

    def test_mcp_fixture_file(self):
        raw = json.loads((Path(__file__).parent / "fixtures" / "mcp_snapshot.json").read_text(encoding="utf-8"))
        a = A.analyze(normalize(raw), [], NOW)
        self.assertEqual(a["code_status"], A.AKTIVT)
        self.assertEqual(a["review_status"], [A.UNDER_GRANSKNING])
        self.assertEqual(a["setup_commit_count"], 1)

    def test_swedish_dates(self):
        self.assertEqual(fmt_date("2026-11-24T10:00:00Z"), "24 november 2026")


if __name__ == "__main__":
    unittest.main()
