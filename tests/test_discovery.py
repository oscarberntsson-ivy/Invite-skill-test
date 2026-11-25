"""Tester för att hitta kandidater och deras repositories (utan lokal lagring)."""

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

from repo_monitor import discovery, issues  # noqa: E402
from repo_monitor.cli import main  # noqa: E402


def issue(number, name, username, created="2026-11-10T10:00:00Z", labels=("create-repo",), state="open"):
    body = (f"### Namn\n\n{name}\n\n### GitHub-användarnamn\n\n{username}\n\n"
            "### Övrigt\n\n_No response_")
    return {"number": number, "title": f"[Kandidat]: {name}", "body": body, "state": state,
            "created_at": created, "labels": [{"name": l} for l in labels]}


ISSUES = {"issues": [
    issue(1, "Anna Andersson", "anna-a"),
    issue(2, "Erik Eriksson", "@erik-e"),
    issue(3, "Åsa Öberg", "asa-o"),
    {"number": 4, "title": "Annat", "body": "Bara en fråga", "state": "open", "labels": []},
], "pageInfo": {}}
REPOS = {"items": [
    {"full_name": "IvyTechSE/ivy-engineering-challenge-anna-a", "created_at": "2026-11-10T10:05:00Z"},
    {"full_name": "IvyTechSE/ivy-engineering-challange-erik-e"},    # felstavat prefix
    {"full_name": "IvyTechSE/ivy-engineering-challenge-ny-person"},  # ingen issue
    {"full_name": "IvyTechSE/ivy-engineering-challenge"},            # mallrepo
    {"full_name": "AnnanOrg/ivy-engineering-challenge-x"},           # fel ägare
]}


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.home = Path(self._tmp.name)
        os.environ["REPO_MONITOR_HOME"] = str(self.home)
        issues.save_config({**issues.default_config(), "repository": "IvyTechSE/admin",
                            "template_path": ".github/ISSUE_TEMPLATE/bjud-in.yml", "enabled": True})
        self.cfg = discovery.load_config()

    def tearDown(self):
        os.environ.pop("REPO_MONITOR_HOME", None)
        self._tmp.cleanup()

    def cli(self, *argv, stdin=""):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err), mock.patch("sys.stdin", io.StringIO(stdin)):
            code = main(list(argv))
        return code, out.getvalue(), err.getvalue()


class TestParsing(unittest.TestCase):
    cfg = discovery.default_config()

    def test_username_from_repo_both_spellings(self):
        self.assertEqual(discovery.username_from_repo("ivy-engineering-challenge-anna-a", self.cfg), "anna-a")
        self.assertEqual(discovery.username_from_repo("ivy-engineering-challange-erik", self.cfg), "erik")
        self.assertIsNone(discovery.username_from_repo("ivy-engineering-challenge", self.cfg))

    def test_parse_issue_bodies(self):
        self.assertEqual(discovery.parse_issue_body(issue(1, "Anna", "anna")["body"]),
                         {"Namn": "Anna", "GitHub-användarnamn": "anna", "Övrigt": None})
        self.assertEqual(discovery.parse_issue_body("**Namn:** Anna\nGitHub username: anna")["Namn"], "Anna")

    def test_person_from_issue_cleans_username(self):
        self.assertEqual(discovery.person_from_issue(issue(2, "E", "@erik-e"), self.cfg, "o/r")["username"], "erik-e")
        body = "### Name\n\nKim\n\n### GitHub username\n\nhttps://github.com/kim99"
        self.assertEqual(discovery.person_from_issue({"body": body}, self.cfg, None)["username"], "kim99")
        self.assertIsNone(discovery.person_from_issue({"body": "### Namn\n\nX"}, self.cfg, None))


class TestPeople(Base):
    def test_people_with_issues_and_repos(self):
        r = discovery.people(ISSUES, REPOS, self.cfg)
        by_user = {p["username"]: p for p in r["people"]}
        self.assertEqual(sorted(by_user), ["anna-a", "asa-o", "erik-e", "ny-person"])
        self.assertEqual(by_user["anna-a"]["name"], "Anna Andersson")
        self.assertEqual(by_user["anna-a"]["repository"], "IvyTechSE/ivy-engineering-challenge-anna-a")
        self.assertEqual(by_user["anna-a"]["issue_url"], "https://github.com/IvyTechSE/admin/issues/1")
        self.assertTrue(by_user["anna-a"]["repo_found"])
        self.assertEqual(by_user["erik-e"]["repository"], "IvyTechSE/ivy-engineering-challange-erik-e")
        self.assertFalse(by_user["asa-o"]["repo_found"])
        self.assertIsNone(by_user["ny-person"]["name"])
        self.assertEqual(r["issues_without_username"], [4])

    def test_people_issues_only(self):
        r = discovery.people(ISSUES, None, self.cfg)
        self.assertEqual(len(r["people"]), 3)
        self.assertTrue(all(p["repo_found"] is None for p in r["people"]))
        self.assertFalse(r["repos_searched"])

    def test_label_filter_and_latest_issue_wins(self):
        cfg = {**self.cfg, "issue_labels": ["create-repo"]}
        data = [issue(1, "Gammalt", "anna-a", "2026-11-01T00:00:00Z"),
                issue(7, "Anna Andersson", "anna-a", "2026-11-05T00:00:00Z"),
                issue(8, "Ignorera", "x", labels=("annat",))]
        r = discovery.people(data, None, cfg)
        self.assertEqual([(p["username"], p["issue_number"]) for p in r["people"]], [("anna-a", 7)])

    def test_find(self):
        ppl = discovery.people(ISSUES, None, self.cfg)["people"]
        self.assertEqual([p["username"] for p in discovery.find(ppl, "anna")], ["anna-a"])
        self.assertEqual([p["username"] for p in discovery.find(ppl, "asa")], ["asa-o"])  # accentokänsligt
        self.assertEqual([p["username"] for p in discovery.find(ppl, "Erik Eriksson")], ["erik-e"])
        self.assertEqual([p["username"] for p in discovery.find(ppl, "@erik-e")], ["erik-e"])
        self.assertEqual(discovery.find(ppl, "ingen"), [])


class TestCli(Base):
    def test_people_command(self):
        stdin = json.dumps({"issues": ISSUES, "repos": REPOS})
        code, out, err = self.cli("people", stdin=stdin)
        self.assertEqual(code, 0, err)
        self.assertIn("Anna Andersson (GitHub: anna-a): IvyTechSE/ivy-engineering-challenge-anna-a, inbjudan #1", out)
        self.assertIn("asa-o): IvyTechSE/ivy-engineering-challenge-asa-o, inbjudan #3 – **repot hittades inte**", out)
        self.assertIn("#4", out)

        code, out, _ = self.cli("people", "--query", "Åsa", "--format", "json", stdin=stdin)
        data = json.loads(out)
        self.assertEqual([p["username"] for p in data["people"]], ["asa-o"])
        self.assertEqual(data["people"][0]["snapshot_person"]["name"], "Åsa Öberg")

        code, _, err = self.cli("people", stdin='{"x": 1}')
        self.assertEqual(code, 2)

    def test_configure(self):
        code, _, err = self.cli("discover", "configure", "--pattern", "^utan-grupp$")
        self.assertEqual(code, 2)
        self.assertIn("username", err)
        code, out, _ = self.cli("discover", "configure", "--owner", "AnnanOrg",
                                "--name-field", "Ditt namn", "--username-field", "Ditt GitHub-konto")
        self.assertEqual(code, 0)
        cfg = discovery.load_config()
        self.assertEqual(cfg["owner"], "AnnanOrg")
        self.assertEqual(cfg["issue_fields"]["name"], ["Ditt namn"])
        self.assertIn("IvyTechSE/admin", out)


if __name__ == "__main__":
    unittest.main()
