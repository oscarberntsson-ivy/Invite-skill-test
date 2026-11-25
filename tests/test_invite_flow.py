"""Hela flödet: bjud in kandidat -> issue skapas -> har kandidaten committat något?"""

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
from repo_monitor import issues, storage  # noqa: E402
from repo_monitor.cli import main  # noqa: E402

FIX = Path(__file__).parent / "fixtures"


class TestInviteFlow(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.home = Path(self._tmp.name)
        os.environ["REPO_MONITOR_HOME"] = str(self.home)
        self.cli("issue", "configure", "--repository", "IvyTechSE/kodutmaning-admin",
                 "--template-path", ".github/ISSUE_TEMPLATE/bjud-in.yml", "--enable")
        self.tpl = self.home / "template.yml"
        self.tpl.write_text((FIX / "invite_form.yml").read_text(encoding="utf-8"), encoding="utf-8")

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

    def snapshot(self, commits, ok=True):
        name = "ivy-engineering-challenge-anna-a"
        if not ok:
            return self.write("snap.json", F.inaccessible(name, "IvyTechSE"))
        return self.write("snap.json", F.snapshot(F.repo(name, owner="IvyTechSE"), {"main": commits}))

    def test_full_flow(self):
        # 1. Agenten visar templatens frågor
        code, out, _ = self.cli("issue", "questions", str(self.tpl))
        self.assertEqual(code, 0)
        self.assertIn("1. **Namn** (**obligatorisk**)", out)
        self.assertIn("2. **GitHub-användarnamn** (**obligatorisk**)", out)
        self.assertIn("`Junior` · `Senior`", out)

        # 2. Användaren svarar -> utkast
        answers = self.write("answers.json", {"name": "Anna Andersson", "github_username": "anna-a",
                                              "level": "Junior", "title": "Anna Andersson"})
        meta = self.write("meta.json", {"labels_existing": ["invite-candidate"], "assignable": None})
        code, out, _ = self.cli("issue", "draft", "--template-file", str(self.tpl),
                                "--answers", answers, "--repo-meta", meta)
        self.assertEqual(code, 0, out)
        draft_id = out.split("Utkast-id: `")[1].split("`")[0]
        payload = json.loads(self.cli("issue", "payload", draft_id)[1])
        self.assertEqual(payload["title"], "[Kandidat]: Anna Andersson")

        # 3. Spärren frågar, issuen skapas, kandidaten registreras automatiskt
        self.assertEqual(issues.check_issue_write(payload)[0], "ask")
        issues.record_created(payload, {"url": "https://github.com/IvyTechSE/kodutmaning-admin/issues/12"})
        entry = storage.find_entry(storage.load_registry(), "IvyTechSE", "ivy-engineering-challenge-anna-a")
        self.assertEqual(entry["person_name"], "Anna Andersson")
        self.assertEqual(entry["invitation_issue"], 12)
        code, out, _ = self.cli("registry", "find", "anna")
        self.assertIn("ivy-engineering-challenge-anna-a", out)

        # 4a. Repot finns inte ännu
        code, out, _ = self.cli("analyze", self.snapshot([], ok=False), "--view", "candidate",
                                "--now", "2026-11-25T08:00:00Z")
        self.assertIn("**Okänt**", out)
        self.assertIn("kanske inte skapats ännu", out)

        # 4b. Repot finns, inga commits från kandidaten (bara automatisk startcommit)
        code, out, _ = self.cli("analyze", self.snapshot([F.commit("repo-bot", "2026-11-01T09:00:30Z")]),
                                "--view", "candidate", "--now", "2026-11-25T09:00:00Z")
        self.assertIn("**Nej** – Anna Andersson (anna-a) har inte committat något", out)
        self.assertIn("baslinje", out)
        self.assertNotIn("Kontrollen har sparats", out)

        # 4c. Kandidaten har committat (en annan persons commit räknas inte)
        commits = [F.commit("anna-a", "2026-11-25T10:00:00Z"), F.commit("anna-a", "2026-11-24T10:00:00Z"),
                   F.commit("someone-else", "2026-11-23T10:00:00Z")]
        code, out, _ = self.cli("analyze", self.snapshot(commits), "--view", "candidate",
                                "--now", "2026-11-25T12:00:00Z")
        self.assertIn("**Ja** – Anna Andersson (anna-a) har gjort 2 commits", out)
        self.assertIn("senast 25 november 2026", out)
        self.assertIn("2 nya", out)

        # 4d. Ingen ny aktivitet sedan förra kontrollen
        code, out, _ = self.cli("analyze", self.snapshot(commits), "--view", "candidate",
                                "--now", "2026-11-26T12:00:00Z")
        self.assertIn("**Ja**", out)
        self.assertIn("inga nya", out)

    def test_issue_without_username_warns(self):
        cfg = issues.load_config()
        draft = {"payload": {"body": "### Namn\n\nAnna"}, "issue_number": 1, "repository": cfg["repository"]}
        issues.after_created(draft)
        self.assertIsNone(draft["registered_repository"])
        self.assertTrue(any("användarnamn" in w for w in draft["warnings"]))


if __name__ == "__main__":
    unittest.main()
