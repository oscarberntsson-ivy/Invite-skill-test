"""Hela flödet utan lokal lagring:
bjud in kandidat -> issue skapas på GitHub -> "har kandidaten committat något?"
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
from repo_monitor import issues  # noqa: E402
from repo_monitor.cli import main  # noqa: E402

TEMPLATE = (Path(__file__).parent / "fixtures" / "invite_form.yml").read_text(encoding="utf-8")


class TestInviteFlow(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.home = Path(self._tmp.name)
        os.environ["REPO_MONITOR_HOME"] = str(self.home)
        self.cli("issue", "configure", "--repository", "IvyTechSE/kodutmaning-admin",
                 "--template-path", ".github/ISSUE_TEMPLATE/bjud-in.yml", "--enable")

    def tearDown(self):
        os.environ.pop("REPO_MONITOR_HOME", None)
        self._tmp.cleanup()

    def cli(self, *argv, stdin=""):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err), mock.patch("sys.stdin", io.StringIO(stdin)):
            code = main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_full_flow(self):
        # 1. Agenten visar templatens frågor
        code, out, _ = self.cli("issue", "questions", stdin=TEMPLATE)
        self.assertIn("1. **Namn** (**obligatorisk**)", out)
        self.assertIn("2. **GitHub-användarnamn** (**obligatorisk**)", out)
        self.assertIn("`Junior` · `Senior`", out)

        # 2. Användaren svarar -> utkast (inga tidigare inbjudningar på GitHub)
        data = {"template": TEMPLATE,
                "answers": {"name": "Anna Andersson", "github_username": "anna-a", "level": "Junior",
                            "title": "Anna Andersson"},
                "meta": {"labels_existing": ["invite-candidate"]},
                "existing_issues": {"issues": []}}
        code, out, _ = self.cli("issue", "draft", stdin=json.dumps(data))
        self.assertEqual(code, 0, out)
        payload = json.loads(out.split("```json\n")[1].split("\n```")[0])
        self.assertEqual(payload["title"], "[Kandidat]: Anna Andersson")
        self.assertEqual(issues.check_issue_write(payload)[0], "ask")

        # 3. Issuen finns nu på GitHub. Ett nytt försök stoppas som dubblett.
        created = {"number": 12, "title": payload["title"], "body": payload["body"], "state": "open",
                   "created_at": "2026-11-25T08:00:00Z", "labels": [{"name": "invite-candidate"}]}
        code, out, _ = self.cli("issue", "draft", stdin=json.dumps({**data, "existing_issues": {"issues": [created]}}))
        self.assertEqual(code, 3)
        self.assertIn("redan en öppen inbjudan", out)

        # 4. Senare: "Har Anna committat något?" – kandidaten hittas via issuen på GitHub
        code, out, _ = self.cli("people", "--query", "anna", "--format", "json",
                                stdin=json.dumps({"issues": {"issues": [created]}, "repos": None}))
        person = json.loads(out)["people"][0]
        self.assertEqual(person["repository"], "IvyTechSE/ivy-engineering-challenge-anna-a")

        def ask(snapshot, *extra):
            snap = {**snapshot, "person": person["snapshot_person"]}
            return self.cli("analyze", "--view", "candidate", *extra, stdin=json.dumps(snap))[1]

        name = "ivy-engineering-challenge-anna-a"
        out = ask(F.inaccessible(name, "IvyTechSE"))
        self.assertIn("**Okänt**", out)
        self.assertIn("kanske inte skapats ännu", out)

        out = ask(F.snapshot(F.repo(name, owner="IvyTechSE"), {"main": [F.commit("repo-bot", "2026-11-01T09:00:30Z")]}))
        self.assertIn("**Nej** – Anna Andersson (anna-a) har inte committat något", out)

        commits = [F.commit("anna-a", "2026-11-25T10:00:00Z"), F.commit("anna-a", "2026-11-24T10:00:00Z"),
                   F.commit("someone-else", "2026-11-23T10:00:00Z")]
        out = ask(F.snapshot(F.repo(name, owner="IvyTechSE"), {"main": commits}))
        self.assertIn("**Ja** – Anna Andersson (anna-a) har gjort 2 commits", out)
        self.assertIn("senast 25 november 2026", out)

        out = ask(F.snapshot(F.repo(name, owner="IvyTechSE"), {"main": commits}), "--since", "2026-11-25")
        self.assertIn("Sedan 25 november 2026: 1 commit.", out)

        # Inget har sparats lokalt – bara inställningen
        self.assertEqual(sorted(p.name for p in self.home.iterdir()), ["issue-config.json"])


if __name__ == "__main__":
    unittest.main()
