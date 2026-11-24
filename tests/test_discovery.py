"""Tester för att hitta challenge-repositories och koppla dem till personer via issues."""

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
from repo_monitor import discovery, issues, render, storage  # noqa: E402
from repo_monitor.cli import main  # noqa: E402
from repo_monitor.snapshot import normalize  # noqa: E402
from repo_monitor.timeutil import parse_iso  # noqa: E402

NOW = parse_iso("2026-11-24T12:00:00Z")


def issue(number, name, username, created="2026-11-10T10:00:00Z", labels=("create-repo",)):
    body = (f"### Namn\n\n{name}\n\n### GitHub-användarnamn\n\n{username}\n\n"
            "### Övrigt\n\n_No response_")
    return {"number": number, "title": f"[Nytt repo]: {username}", "body": body, "state": "open",
            "created_at": created, "labels": [{"name": l} for l in labels]}


ISSUES = {"issues": [
    issue(1, "Anna Andersson", "anna-a"),
    issue(2, "Erik Eriksson", "@erik-e"),
    issue(3, "Åsa Öberg", "asa-o"),
    {"number": 4, "title": "Annat", "body": "Bara en fråga", "state": "open", "labels": []},
], "pageInfo": {}}
REPOS = {"items": [
    {"full_name": "IvyTechSE/ivy-engineering-challenge-anna-a", "created_at": "2026-11-10T10:05:00Z",
     "html_url": "https://github.com/IvyTechSE/ivy-engineering-challenge-anna-a"},
    {"full_name": "IvyTechSE/ivy-engineering-challange-erik-e"},   # felstavat prefix
    {"full_name": "IvyTechSE/ivy-engineering-challenge-ny-person"},  # ingen issue
    {"full_name": "IvyTechSE/ivy-engineering-challenge"},           # mallrepo, inte en deltagare
    {"full_name": "AnnanOrg/ivy-engineering-challenge-x"},          # fel ägare
]}


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.home = Path(self._tmp.name)
        os.environ["REPO_MONITOR_HOME"] = str(self.home)
        issues.save_config({**issues.default_config(), "repository": "IvyTechSE/bestallningar",
                            "template_path": ".github/ISSUE_TEMPLATE/nytt.yml", "enabled": True})

    def tearDown(self):
        os.environ.pop("REPO_MONITOR_HOME", None)
        self._tmp.cleanup()

    def cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def write(self, name, data):
        p = self.home / name
        p.write_text(json.dumps(data), encoding="utf-8")
        return str(p)


class TestParsing(unittest.TestCase):
    cfg = discovery.default_config()

    def test_username_from_repo_both_spellings(self):
        self.assertEqual(discovery.username_from_repo("ivy-engineering-challenge-anna-a", self.cfg), "anna-a")
        self.assertEqual(discovery.username_from_repo("ivy-engineering-challange-erik", self.cfg), "erik")
        self.assertIsNone(discovery.username_from_repo("ivy-engineering-challenge", self.cfg))
        self.assertIsNone(discovery.username_from_repo("something-else", self.cfg))

    def test_parse_issue_form_body(self):
        a = discovery.parse_issue_body(issue(1, "Anna", "anna")["body"])
        self.assertEqual(a, {"Namn": "Anna", "GitHub-användarnamn": "anna", "Övrigt": None})

    def test_parse_plain_label_lines(self):
        a = discovery.parse_issue_body("**Namn:** Anna\nGitHub username: anna")
        self.assertEqual(a["Namn"], "Anna")

    def test_person_from_issue_cleans_username(self):
        p = discovery.person_from_issue(issue(2, "Erik", "@erik-e"), self.cfg, "o/r")
        self.assertEqual(p["username"], "erik-e")
        self.assertEqual(p["issue_url"], "https://github.com/o/r/issues/2")
        body = "### Name\n\nKim\n\n### GitHub username\n\nhttps://github.com/kim99"
        self.assertEqual(discovery.person_from_issue({"number": 5, "body": body}, self.cfg, None)["username"], "kim99")
        self.assertIsNone(discovery.person_from_issue({"number": 6, "body": "### Namn\n\nX"}, self.cfg, None))


class TestSync(Base):
    def test_sync_with_issues_and_repos(self):
        reg = storage.load_registry()
        res = discovery.sync(reg, ISSUES, REPOS, discovery.load_config())
        names = sorted(f"{e['owner']}/{e['name']}" for e in reg["repositories"])
        self.assertEqual(names, [
            "IvyTechSE/ivy-engineering-challange-erik-e",
            "IvyTechSE/ivy-engineering-challenge-anna-a",
            "IvyTechSE/ivy-engineering-challenge-asa-o",
            "IvyTechSE/ivy-engineering-challenge-ny-person",
        ])
        anna = storage.find_entry(reg, "IvyTechSE", "ivy-engineering-challenge-anna-a")
        self.assertEqual(anna["person_name"], "Anna Andersson")
        self.assertEqual(anna["project_name"], "Anna Andersson")
        self.assertEqual(anna["invited_contributors"], ["anna-a"])
        self.assertEqual(anna["invitation_issue"], 1)
        self.assertEqual(anna["created_at"], "2026-11-10T10:05:00Z")
        self.assertTrue(anna["repo_verified"])
        self.assertEqual(res["repos_not_found"], ["IvyTechSE/ivy-engineering-challenge-asa-o"])
        self.assertEqual(res["repos_without_issue"], ["IvyTechSE/ivy-engineering-challenge-ny-person"])
        self.assertEqual(res["issues_without_username"], [4])
        ny = storage.find_entry(reg, "IvyTechSE", "ivy-engineering-challenge-ny-person")
        self.assertEqual(ny["project_name"], "ny-person")

    def test_sync_issues_only_and_idempotent(self):
        reg = storage.load_registry()
        discovery.sync(reg, ISSUES, None, discovery.load_config())
        self.assertEqual(len(reg["repositories"]), 3)
        self.assertIsNone(storage.find_entry(reg, "IvyTechSE", "ivy-engineering-challenge-anna-a").get("repo_verified"))
        res = discovery.sync(reg, ISSUES, None, discovery.load_config())
        self.assertEqual(len(reg["repositories"]), 3)
        self.assertEqual(res["added"], [])

    def test_label_filter_and_latest_issue_wins(self):
        cfg = {**discovery.load_config(), "issue_labels": ["create-repo"]}
        data = [issue(1, "Gammalt namn", "anna-a", "2026-11-01T00:00:00Z"),
                issue(7, "Anna Andersson", "anna-a", "2026-11-05T00:00:00Z"),
                issue(8, "Ignorera", "x", labels=("annat",))]
        reg = storage.load_registry()
        discovery.sync(reg, data, None, cfg)
        self.assertEqual(len(reg["repositories"]), 1)
        self.assertEqual(reg["repositories"][0]["invitation_issue"], 7)

    def test_manual_project_name_is_kept(self):
        reg = storage.load_registry()
        storage.upsert_entry(reg, "IvyTechSE", "ivy-engineering-challenge-anna-a", project_name="Specialnamn")
        discovery.sync(reg, ISSUES, None, discovery.load_config())
        e = storage.find_entry(reg, "IvyTechSE", "ivy-engineering-challenge-anna-a")
        self.assertEqual(e["project_name"], "Specialnamn")
        self.assertEqual(e["person_name"], "Anna Andersson")

    def test_find(self):
        reg = storage.load_registry()
        discovery.sync(reg, ISSUES, None, discovery.load_config())
        self.assertEqual([e["github_username"] for e in discovery.find(reg, "anna")], ["anna-a"])
        self.assertEqual([e["github_username"] for e in discovery.find(reg, "asa")], ["asa-o"])   # accentokänsligt
        self.assertEqual([e["github_username"] for e in discovery.find(reg, "Erik Eriksson")], ["erik-e"])
        self.assertEqual([e["github_username"] for e in discovery.find(reg, "@erik-e")], ["erik-e"])
        self.assertEqual(discovery.find(reg, "ingen"), [])


class TestReportsUsePersonNames(Base):
    def test_contributor_and_header_show_person(self):
        reg = storage.load_registry()
        discovery.sync(reg, ISSUES, REPOS, discovery.load_config())
        entry = storage.find_entry(reg, "IvyTechSE", "ivy-engineering-challenge-anna-a")
        raw = F.snapshot(F.repo("ivy-engineering-challenge-anna-a", owner="IvyTechSE"),
                         {"main": [F.commit("anna-a", "2026-11-20T10:00:00Z", name="anna-a")]})
        a = A.analyze(normalize(raw), entry, None, [], NOW)
        self.assertEqual(a["last_contributor"], "Anna Andersson (anna-a)")
        md = render.render(a, "report")
        self.assertIn("**Person:** Anna Andersson (GitHub: anna-a)", md)
        self.assertIn("Beställd via issue:** [#1]", md)
        self.assertIn("#### Anna Andersson (anna-a)", md)

    def test_unavailable_repo_from_issue_mentions_action(self):
        reg = storage.load_registry()
        discovery.sync(reg, ISSUES, None, discovery.load_config())
        entry = storage.find_entry(reg, "IvyTechSE", "ivy-engineering-challenge-asa-o")
        a = A.analyze(normalize(F.inaccessible("ivy-engineering-challenge-asa-o", "IvyTechSE")), entry, None, [], NOW)
        self.assertIn("GitHub Action kan ha misslyckats", render.render(a))


class TestCli(Base):
    def test_sync_find_and_configure(self):
        i = self.write("issues.json", ISSUES)
        r = self.write("repos.json", REPOS)
        code, out, err = self.cli("discover", "sync", "--issues", i, "--repos", r)
        self.assertEqual(code, 0, err)
        self.assertIn("Personer identifierade från issues: 3", out)
        self.assertIn("ivy-engineering-challenge-asa-o (GitHub Action kan ha misslyckats", out)
        code, out, _ = self.cli("registry", "find", "Åsa")
        self.assertIn("Åsa Öberg: IvyTechSE/ivy-engineering-challenge-asa-o", out)
        code, out, _ = self.cli("registry", "list")
        self.assertIn("– Anna Andersson", out)

        code, _, err = self.cli("discover", "configure", "--pattern", "^utan-grupp$")
        self.assertEqual(code, 2)
        self.assertIn("username", err)
        code, out, _ = self.cli("discover", "configure", "--owner", "AnnanOrg",
                                "--name-field", "Ditt namn", "--username-field", "Ditt GitHub-konto")
        self.assertEqual(code, 0)
        cfg = discovery.load_config()
        self.assertEqual(cfg["owner"], "AnnanOrg")
        self.assertEqual(cfg["issue_fields"]["name"], ["Ditt namn"])
        self.assertIn("IvyTechSE/bestallningar", out)

        code, _, err = self.cli("discover", "sync")
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
