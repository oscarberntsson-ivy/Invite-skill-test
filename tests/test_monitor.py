"""Tester för GitHub Repository Monitor med mockad GitHub-data.

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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import factories as F  # noqa: E402
from repo_monitor import analysis as A  # noqa: E402
from repo_monitor import render, storage  # noqa: E402
from repo_monitor.cli import main  # noqa: E402
from repo_monitor.snapshot import normalize  # noqa: E402
from repo_monitor.timeutil import fmt_date, parse_iso  # noqa: E402

NOW = parse_iso("2026-11-24T12:00:00Z")
LATER = parse_iso("2026-11-25T12:00:00Z")


def run(raw, prev=None, entry=None, automation=("repo-bot",), now=NOW):
    snap = normalize(raw)
    return A.analyze(snap, entry, prev, list(automation), now), snap


class TempHome(unittest.TestCase):
    """Bas för tester som skriver till disk: isolerad datakatalog."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.home = Path(self._tmp.name)
        os.environ["REPO_MONITOR_HOME"] = str(self.home)

    def tearDown(self):
        os.environ.pop("REPO_MONITOR_HOME", None)
        self._tmp.cleanup()

    def write(self, name, data):
        p = self.home / f"{name}.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        return str(p)

    def cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(list(argv))
        return code, out.getvalue(), err.getvalue()


# ---------------------------------------------------------------------------
# 1. Repository utan commits
# ---------------------------------------------------------------------------
class TestNoCommits(unittest.TestCase):
    def test_empty_repository_is_inactive(self):
        a, _ = run(F.snapshot(F.repo(), {"main": []}))
        self.assertEqual(a["code_status"], A.INAKTIVT)
        self.assertEqual(a["commit_count"], 0)
        self.assertEqual(a["contributor_count"], 0)
        self.assertIsNone(a["last_activity"])
        self.assertEqual(a["review_status"], [A.INGA_PR])

    def test_real_empty_repository_from_mcp(self):
        # GitHub svarar 409 "Git Repository is empty" och list_branches ger [].
        raw = {"repo": {"owner": "o", "name": "tomt", "created_at": None}, "branches": [],
               "commits_by_branch": {}, "pull_requests": []}
        a, _ = run(raw)
        self.assertEqual(a["code_status"], A.INAKTIVT)
        self.assertEqual(a["commit_count"], 0)
        md = render.render(a, "status")
        self.assertIn("inga ännu (repositoryt är tomt)", md)
        self.assertIn("Skapandedatum kunde inte hämtas", md)
        self.assertNotIn("Kör kontrollen igen", md)

    def test_setup_commit_from_automation_is_not_a_contribution(self):
        a, _ = run(F.snapshot(F.repo(), {"main": [F.setup_commit()]}))
        self.assertEqual(a["code_status"], A.INAKTIVT)
        self.assertEqual(a["setup_commit_count"], 1)
        self.assertEqual(a["commit_count"], 0)

    def test_initial_commit_right_after_creation_is_setup_even_without_bot(self):
        c = F.commit("oscar", "2026-11-01T09:01:00Z", "Initial commit")
        a, _ = run(F.snapshot(F.repo(), {"main": [c]}), automation=())
        self.assertEqual(a["code_status"], A.INAKTIVT)
        self.assertEqual(a["setup_commit_count"], 1)

    def test_report_says_inactive_but_does_not_claim_nobody_works(self):
        entry = {"invited_contributors": ["anna"], "project_name": "Min app"}
        a, _ = run(F.snapshot(F.repo(), {"main": []}), entry=entry)
        md = render.render(a, "status")
        self.assertIn("KODSTATUS: INAKTIVT", md)
        self.assertIn("inte nödvändigtvis att ingen arbetar", md)
        self.assertIn("anna", md)
        self.assertEqual(a["invited_inactive"], ["anna"])


# ---------------------------------------------------------------------------
# 2. Repository med en commit
# ---------------------------------------------------------------------------
class TestOneCommit(unittest.TestCase):
    def test_single_commit_is_started(self):
        c = F.commit("anna", "2026-11-20T14:05:00Z", "Add login page", name="Anna Andersson")
        a, _ = run(F.snapshot(F.repo(pushed_at="2026-11-20T14:06:00Z"), {"main": [c, F.setup_commit()]}))
        self.assertEqual(a["code_status"], A.PABORJAT)
        self.assertEqual(a["commit_count"], 1)
        self.assertEqual(a["contributor_count"], 1)
        self.assertEqual(a["last_contributor"], "Anna Andersson (anna)")
        self.assertEqual(a["last_push"], "2026-11-20T14:06:00Z")
        md = render.render(a, "report")
        self.assertIn("KODSTATUS: PÅBÖRJAT", md)
        self.assertIn("Add login page", md)
        self.assertIn("20 november 2026", md)

    def test_events_are_kept_separate(self):
        c = F.commit("anna", "2026-11-20T14:05:00Z")
        a, _ = run(F.snapshot(F.repo(pushed_at="2026-11-20T14:06:00Z"), {"main": [c, F.setup_commit()]}))
        types = {e["type"] for e in a["events"]}
        self.assertEqual(types, {A.EV_REPO_CREATED, A.EV_SETUP_COMMIT, A.EV_COMMIT, A.EV_PUSH})
        self.assertEqual(a["last_activity"]["type"], A.EV_PUSH)


# ---------------------------------------------------------------------------
# 3. Repository med flera contributors
# ---------------------------------------------------------------------------
class TestMultipleContributors(unittest.TestCase):
    def test_two_contributors_is_active(self):
        commits = [
            F.commit("erik", "2026-11-21T10:00:00Z", "Add authentication middleware",
                     files=["src/auth.js"]),
            F.commit("anna", "2026-11-20T10:00:00Z", "Create landing page"),
            F.commit("anna", "2026-11-20T11:00:00Z", "Fix typo"),
        ]
        a, _ = run(F.snapshot(F.repo(), {"main": commits}))
        self.assertEqual(a["code_status"], A.AKTIVT)
        self.assertEqual(a["contributor_count"], 2)
        anna = next(p for p in a["contributors"] if p["login"] == "anna")
        self.assertEqual(anna["commits"], 2)
        erik = next(p for p in a["contributors"] if p["login"] == "erik")
        self.assertEqual(erik["files"], ["src/auth.js"])
        self.assertEqual(a["last_contributor"], "Erik")
        md = render.render(a, "contributors")
        self.assertIn("#### Anna", md)
        self.assertIn("Add authentication middleware", md)
        self.assertIn("`src/auth.js`", md)

    def test_one_person_on_several_days_is_active(self):
        commits = [F.commit("anna", "2026-11-20T10:00:00Z"), F.commit("anna", "2026-11-22T10:00:00Z")]
        a, _ = run(F.snapshot(F.repo(), {"main": commits}))
        self.assertEqual(a["code_status"], A.AKTIVT)

    def test_one_person_one_day_several_commits_is_started(self):
        commits = [F.commit("anna", "2026-11-20T10:00:00Z"), F.commit("anna", "2026-11-20T12:00:00Z")]
        a, _ = run(F.snapshot(F.repo(), {"main": commits}))
        self.assertEqual(a["code_status"], A.PABORJAT)


# ---------------------------------------------------------------------------
# 4. Repository med flera branches
# ---------------------------------------------------------------------------
class TestMultipleBranches(unittest.TestCase):
    def test_commits_are_deduplicated_across_branches(self):
        base = F.setup_commit()
        shared = F.commit("anna", "2026-11-20T10:00:00Z", "Shared work")
        feature_only = F.commit("anna", "2026-11-20T11:00:00Z", "Feature work")
        a, _ = run(F.snapshot(F.repo(), {
            "main": [base],
            "feature/login": [feature_only, shared, base],
            "dev": [shared, base],
        }))
        self.assertEqual(a["commit_count"], 2)
        self.assertEqual(a["commits_on_default_branch"], 0)
        names = {b["name"]: b["commits"] for b in a["side_branches"]}
        self.assertEqual(names, {"feature/login": 2, "dev": 1})
        md = render.render(a, "status")
        self.assertIn("sidogrenar", md)
        self.assertIn("feature/login", md)
        anna = a["contributors"][0]
        self.assertCountEqual(anna["branches"], ["feature/login", "dev"])


# ---------------------------------------------------------------------------
# 5. Repository med öppna pull requests
# ---------------------------------------------------------------------------
class TestOpenPullRequests(unittest.TestCase):
    def test_open_pr_gives_under_review_alongside_code_status(self):
        c = F.commit("anna", "2026-11-20T10:00:00Z")
        a, _ = run(F.snapshot(F.repo(), {"main": [F.setup_commit()], "feature": [c]},
                              prs=[F.pr(1, "Inloggning", "anna")]))
        self.assertEqual(a["code_status"], A.PABORJAT)
        self.assertEqual(a["review_status"], [A.UNDER_GRANSKNING])
        md = render.render(a, "status")
        self.assertIn("UNDER GRANSKNING", md)
        self.assertIn("Koden behöver granskas", md)
        self.assertIn("**Öppna pull requests:** 1", md)

    def test_draft_and_raw_pull_request_shape(self):
        raw = F.pr(7, "WIP", "erik")
        raw["draft"] = True
        a, snap = run(F.snapshot(F.repo(), {"main": []}, prs=[raw]))
        self.assertTrue(snap["pull_requests"][0]["draft"])
        self.assertEqual(a["open_prs"][0]["base"], "main")


# ---------------------------------------------------------------------------
# 6. Repository med mergade pull requests
# ---------------------------------------------------------------------------
class TestMergedPullRequests(unittest.TestCase):
    def test_merged_pr(self):
        c = F.commit("anna", "2026-11-20T10:00:00Z")
        merge = F.commit("oscar", "2026-11-21T10:00:00Z", "Merge pull request #1", parents=2)
        a, _ = run(F.snapshot(F.repo(), {"main": [merge, c, F.setup_commit()]}, prs=[
            F.pr(1, "Inloggning", "anna", merged_at="2026-11-21T10:00:00Z"),
            F.pr(2, "Avbruten idé", "erik", closed_at="2026-11-21T11:00:00Z"),
        ]))
        self.assertEqual(a["review_status"], [A.MERGAT])
        self.assertEqual(a["commit_count"], 1)          # merge-commits räknas separat
        self.assertEqual(a["merge_commit_count"], 1)
        self.assertEqual(len(a["closed_prs"]), 1)
        types = [e["type"] for e in a["events"]]
        self.assertIn(A.EV_PR_MERGED, types)
        self.assertIn(A.EV_PR_CLOSED, types)
        self.assertIn(A.EV_PR_OPENED, types)
        md = render.render(a, "report")
        self.assertIn("GRANSKNING: MERGAT", md)
        self.assertIn("stängdes utan att föras in", md)

    def test_open_and_merged_can_overlap(self):
        a, _ = run(F.snapshot(F.repo(), {"main": []}, prs=[
            F.pr(1, "A", "anna", merged_at="2026-11-21T10:00:00Z"), F.pr(2, "B", "anna")]))
        self.assertEqual(a["review_status"], [A.UNDER_GRANSKNING, A.MERGAT])


# ---------------------------------------------------------------------------
# 7. Ingen ny aktivitet sedan föregående kontroll
# ---------------------------------------------------------------------------
class TestChangesSinceLastCheck(unittest.TestCase):
    def setUp(self):
        self.c1 = F.commit("anna", "2026-11-20T10:00:00Z")
        self.raw = F.snapshot(F.repo(), {"main": [self.c1, F.setup_commit()]},
                              prs=[F.pr(1, "Inloggning", "anna")])

    def _state_after_first(self):
        a, snap = run(self.raw)
        self.assertTrue(a["changes"]["baseline"])
        return A.build_state(a, snap, None)

    def test_first_check_is_baseline(self):
        a, _ = run(self.raw)
        self.assertIn("baslinje", render.render(a, "changes"))

    def test_no_new_activity(self):
        state = self._state_after_first()
        a, _ = run(self.raw, prev=state, now=LATER)
        self.assertFalse(a["changes"]["baseline"])
        self.assertTrue(a["changes"]["nothing_new"])
        self.assertIn("Inget nytt har hänt", render.render(a, "changes"))

    def test_new_commit_contributor_and_merge_detected(self):
        state = self._state_after_first()
        c2 = F.commit("erik", "2026-11-24T09:00:00Z", "Add tests")
        raw = F.snapshot(F.repo(), {"main": [c2, self.c1, F.setup_commit()], "erik-branch": [c2]},
                         prs=[F.pr(1, "Inloggning", "anna", merged_at="2026-11-24T10:00:00Z")])
        a, _ = run(raw, prev=state, now=LATER)
        ch = a["changes"]
        self.assertEqual([c["sha"] for c in ch["new_commits"]], [c2["sha"]])
        self.assertEqual([p["login"] for p in ch["new_contributors"]], ["erik"])
        self.assertEqual([p["number"] for p in ch["merged_prs"]], [1])
        self.assertEqual(ch["new_prs"], [])
        self.assertEqual(ch["new_branches"], ["erik-branch"])
        self.assertIn("main", ch["updated_branches"])
        md = render.render(a, "changes")
        self.assertIn("Ny contributor", md)
        self.assertIn("mergats", md)

    def test_unknown_parts_are_not_reported_as_unchanged(self):
        state = self._state_after_first()
        raw = dict(self.raw)
        raw["pull_requests"] = None
        a, snap = run(raw, prev=state, now=LATER)
        self.assertIn("pull requests", a["changes"]["unknown"])
        self.assertEqual(a["review_status"], [A.OKANT])
        new_state = A.build_state(a, snap, state)
        self.assertEqual(new_state["pull_requests"], {"1": "open"})  # behåller föregående
        self.assertIn("kunde inte kontrolleras", render.render(a, "changes"))


# ---------------------------------------------------------------------------
# 8. Repository som inte är tillgängligt
# ---------------------------------------------------------------------------
class TestInaccessible(unittest.TestCase):
    def test_inaccessible_is_not_inactive(self):
        a, snap = run(F.inaccessible())
        self.assertEqual(a["code_status"], A.EJ_TILLGANGLIGT)
        md = render.render(a, "report")
        self.assertIn("EJ TILLGÄNGLIGT", md)
        self.assertIn("betyder inte att projektet är inaktivt", md)
        self.assertIn("404 Not Found", md)
        self.assertNotIn("INAKTIVT", md.replace("inaktivt", ""))

    def test_state_is_preserved_when_inaccessible(self):
        prev = {"last_checked_at": "2026-11-20T00:00:00Z", "known_commit_shas": ["abc"],
                "contributors": ["anna"], "summary": {"code_status": A.PABORJAT, "commit_count": 1,
                                                      "contributor_count": 1}}
        a, snap = run(F.inaccessible(), prev=prev)
        state = A.build_state(a, snap, prev)
        self.assertEqual(state["last_checked_at"], "2026-11-20T00:00:00Z")
        self.assertEqual(state["known_commit_shas"], ["abc"])
        self.assertFalse(state["last_attempt_ok"])
        self.assertIn("Senast lyckade kontroll", render.render(a))

    def test_partial_failure_commits_unknown(self):
        raw = F.snapshot(F.repo(), {"main": []})
        del raw["commits_by_branch"]
        raw["errors"] = [{"what": "commits", "message": "timeout"}]
        a, _ = run(raw)
        self.assertEqual(a["code_status"], A.OKANT)
        self.assertIsNone(a["commit_count"])
        md = render.render(a, "status")
        self.assertIn("Commits kunde inte hämtas", md)
        self.assertIn("timeout", md)


# ---------------------------------------------------------------------------
# 9. Flera repositories med olika aktivitetsnivåer (via CLI, end-to-end)
# ---------------------------------------------------------------------------
class TestMultipleRepositoriesCli(TempHome):
    def test_overview_and_history(self):
        code, out, _ = self.cli("registry", "add", "testorg/tomt", "--project-name", "Tomt projekt",
                                "--invited", "anna,@erik", "--source", "automation")
        self.assertEqual(code, 0, out)
        self.cli("registry", "add", "testorg/aktivt")
        self.cli("registry", "add", "testorg/hemligt")
        self.cli("registry", "add", "testorg/aldrig-kontrollerat")
        self.cli("registry", "set-automation", "repo-bot")

        s1 = self.write("tomt", F.snapshot(F.repo("tomt"), {"main": [F.setup_commit()]}))
        s2 = self.write("aktivt", F.snapshot(F.repo("aktivt"), {"main": [
            F.commit("anna", "2026-11-20T10:00:00Z"), F.commit("erik", "2026-11-21T10:00:00Z")]},
            prs=[F.pr(3, "Ny funktion", "erik")]))
        s3 = self.write("hemligt", F.inaccessible())

        code, out, err = self.cli("overview", s1, s2, s3, "--now", "2026-11-24T12:00:00Z")
        self.assertEqual(code, 0, err)
        self.assertIn("4 projekt totalt", out)
        self.assertIn("| Tomt projekt | INAKTIVT |", out)
        self.assertIn("| aktivt | AKTIVT | UNDER GRANSKNING |", out)
        self.assertIn("EJ TILLGÄNGLIGT", out)
        self.assertIn("EJ KONTROLLERAT", out)
        self.assertIn("### Inaktiva projekt", out)
        self.assertIn("Första kontrollen (baslinje)", out)

        # Historik sparad, registret uppdaterat med contributors och senaste aktivitet
        self.assertTrue((self.home / "state" / "testorg__aktivt.json").exists())
        reg = storage.load_registry()
        entry = storage.find_entry(reg, "testorg", "aktivt")
        self.assertCountEqual(entry["contributors"], ["anna", "erik"])
        self.assertEqual(entry["last_activity"], "2026-11-21T10:00:00Z")
        tomt = storage.find_entry(reg, "testorg", "tomt")
        self.assertEqual(tomt["invited_contributors"], ["anna", "erik"])

        # Andra kontrollen: inget nytt
        code, out, _ = self.cli("overview", s1, s2, s3, "--now", "2026-11-25T12:00:00Z")
        self.assertIn("Inga nya förändringar", out)

    def test_analyze_report_saves_report_and_changes_view(self):
        self.cli("registry", "add", "testorg/projekt")
        s = self.write("p", F.snapshot(F.repo(), {"main": [F.commit("anna", "2026-11-20T10:00:00Z")]}))
        code, out, err = self.cli("analyze", s, "--view", "report", "--now", "2026-11-24T12:00:00Z")
        self.assertEqual(code, 0, err)
        self.assertIn("baslinje", out)
        self.assertTrue((self.home / "reports" / "testorg__projekt" / "latest.md").exists())
        state = storage.load_state("testorg", "projekt")
        self.assertEqual(state["last_report"], "reports/testorg__projekt/20261124T120000Z.md")

        # status-vyn sparar inte som standard
        code, out, _ = self.cli("analyze", s, "--view", "status", "--now", "2026-11-25T12:00:00Z")
        self.assertEqual(storage.load_state("testorg", "projekt")["last_checked_at"], "2026-11-24T12:00:00Z")

        code, out, _ = self.cli("analyze", s, "--view", "changes", "--now", "2026-11-25T12:00:00Z")
        self.assertIn("Inget nytt har hänt", out)

    def test_json_output_and_errors(self):
        s = self.write("p", F.snapshot(F.repo(), {"main": []}))
        code, out, _ = self.cli("analyze", s, "--format", "json", "--no-save")
        data = json.loads(out)
        self.assertEqual(data["code_status"], A.INAKTIVT)
        self.assertNotIn("_all_commits", data)

        code, _, err = self.cli("analyze", str(self.home / "saknas.json"))
        self.assertEqual(code, 2)
        self.assertIn("finns inte", err)

        bad = self.home / "bad.json"
        bad.write_text("{inte json", encoding="utf-8")
        code, _, err = self.cli("analyze", str(bad))
        self.assertEqual(code, 2)
        self.assertIn("ogiltig JSON", err)

        code, _, err = self.cli("registry", "add", "inte ett repo")
        self.assertEqual(code, 2)

    def test_registry_accepts_urls_and_lists(self):
        self.cli("registry", "add", "https://github.com/TestOrg/Projekt.git", "--created-at", "2026-11-01")
        code, out, _ = self.cli("registry", "list")
        self.assertIn("TestOrg/Projekt", out)
        self.assertIn("1 november 2026", out)
        code, out, _ = self.cli("registry", "remove", "testorg/projekt")
        self.assertEqual(code, 0)
        self.assertEqual(storage.load_registry()["repositories"], [])


# ---------------------------------------------------------------------------
# Normalisering och övrigt
# ---------------------------------------------------------------------------
class TestNormalization(unittest.TestCase):
    def test_simplified_format(self):
        raw = {
            "repo": {"owner": "o", "name": "r", "created_at": F.CREATED},
            "commits": [{"sha": "a" * 40, "author": "anna", "date": "2026-11-20T10:00:00Z",
                         "message": "Hej\n\nlång text", "branches": ["main"], "files": ["x.py"]}],
            "branches": ["main"],
            "pull_requests": [{"number": 1, "title": "t", "state": "OPEN", "author": "anna"}],
        }
        s = normalize(raw)
        self.assertEqual(s["commits"][0]["author_login"], "anna")
        self.assertEqual(s["branches"], [{"name": "main", "sha": None}])
        self.assertEqual(s["pull_requests"][0]["state"], "open")
        a = A.analyze(s, None, None, [], NOW)
        self.assertEqual(a["contributors"][0]["messages"][0]["message"], "Hej")

    def test_missing_sections_mean_unknown_not_empty(self):
        s = normalize({"repo": {"owner": "o", "name": "r"}})
        self.assertIsNone(s["commits"])
        self.assertIsNone(s["pull_requests"])
        self.assertIsNone(s["branches"])

    def test_missing_repo_name_is_a_clear_error(self):
        with self.assertRaises(storage.MonitorError):
            normalize({"commits": []})

    def test_mcp_fixture_file(self):
        raw = json.loads((Path(__file__).parent / "fixtures" / "mcp_snapshot.json").read_text(encoding="utf-8"))
        a = A.analyze(normalize(raw), None, None, [], NOW)
        self.assertEqual(a["code_status"], A.AKTIVT)
        self.assertEqual(a["review_status"], [A.UNDER_GRANSKNING])
        self.assertEqual(a["setup_commit_count"], 1)

    def test_swedish_dates(self):
        self.assertEqual(fmt_date("2026-11-24T10:00:00Z"), "24 november 2026")
        self.assertEqual(fmt_date(None), "okänt datum")


if __name__ == "__main__":
    unittest.main()
