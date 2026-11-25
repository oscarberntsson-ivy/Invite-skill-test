"""Tester för att bjuda in kandidat via issue från den konfigurerade templaten."""

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from repo_monitor import issues, miniyaml  # noqa: E402
from repo_monitor.cli import main  # noqa: E402
from repo_monitor.storage import MonitorError  # noqa: E402

FIX = Path(__file__).parent / "fixtures"
FORM_TEXT = (FIX / "issue_form.yml").read_text(encoding="utf-8")
MD_TEXT = (FIX / "issue_template.md").read_text(encoding="utf-8")
FORM_PATH = ".github/ISSUE_TEMPLATE/nytt-repo.yml"
META_OK = {"labels_existing": ["create-repo", "automation"], "labels_missing": [],
           "assignable": ["oscar-admin", "anna"], "milestones": [{"number": 2, "title": "Hösten"}]}
ANSWERS = {"repo_name": "webshop", "contributors": "anna\nerik",
           "terms": ["Jag har kontrollerat användarnamnen"], "title": "webshop"}


def cfg(**kw):
    c = issues.default_config()
    c.update({"enabled": True, "repository": "minorg/repo-flode", "template_path": FORM_PATH})
    c.update(kw)
    return c


class Home(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.home = Path(self._tmp.name)
        os.environ["REPO_MONITOR_HOME"] = str(self.home)

    def tearDown(self):
        os.environ.pop("REPO_MONITOR_HOME", None)
        self._tmp.cleanup()

    def configure(self, **kw):
        issues.save_config(cfg(**kw))

    def cli(self, *argv, stdin=""):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err), mock.patch("sys.stdin", io.StringIO(stdin)):
            code = main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def payload(self, **kw):
        self.configure(**kw)
        t = issues.parse_template(FORM_TEXT, FORM_PATH)
        d = issues.build_draft(issues.load_config(), t, ANSWERS, META_OK, existing_issues=[])
        self.assertEqual(d["status"], "ready", d)
        return d["payload"]


# ---------------------------------------------------------------------------
class TestYaml(unittest.TestCase):
    def test_mini_parser_matches_pyyaml_on_issue_form(self):
        try:
            import yaml
        except ImportError:  # pragma: no cover
            self.skipTest("PyYAML saknas")
        self.assertEqual(miniyaml.mini_load(FORM_TEXT), yaml.safe_load(FORM_TEXT))

    def test_mini_parser_basics(self):
        data = miniyaml.mini_load('a: 1\nb: "x: y"\nc: [p, "q"]\nd:\n  - e: f\n    g: true\nh: >-\n  one\n  two\n')
        self.assertEqual(data, {"a": 1, "b": "x: y", "c": ["p", "q"], "d": [{"e": "f", "g": True}],
                                "h": "one two"})


class TestTemplateParsing(unittest.TestCase):
    def test_form(self):
        t = issues.parse_template(FORM_TEXT, FORM_PATH)
        self.assertEqual(t["labels"], ["create-repo", "automation"])
        q = {x["key"]: x for x in issues.questions(t)}
        self.assertEqual(list(q), ["repo_name", "contributors", "visibility", "notes", "terms"])
        self.assertTrue(q["repo_name"]["required"])
        self.assertTrue(q["terms"]["required"])
        self.assertFalse(q["notes"]["required"])

    def test_markdown(self):
        t = issues.parse_template(MD_TEXT, ".github/ISSUE_TEMPLATE/nytt.md")
        self.assertEqual(t["headings"], ["Repository-namn", "Contributors"])

    def test_invalid_form(self):
        with self.assertRaises(MonitorError):
            issues.parse_template("name: x\n", FORM_PATH)


# ---------------------------------------------------------------------------
class TestDraft(unittest.TestCase):
    def setUp(self):
        self.t = issues.parse_template(FORM_TEXT, FORM_PATH)

    def test_body_follows_github_issue_form_format(self):
        d = issues.build_draft(cfg(), self.t, ANSWERS, META_OK, existing_issues=[])
        self.assertEqual(d["status"], "ready")
        self.assertEqual(d["payload"]["body"], (
            "### Repository-namn\n\nwebshop\n\n"
            "### Contributors\n\nanna\nerik\n\n"
            "### Synlighet\n\nprivate\n\n"
            "### Övrigt\n\nInget\n\n"
            "### Bekräftelse\n\n- [X] Jag har kontrollerat användarnamnen\n- [ ] Skicka välkomstmail"))
        self.assertEqual(d["payload"]["title"], "[Nytt repo]: webshop")
        self.assertEqual(d["payload"]["labels"], ["create-repo", "automation"])
        self.assertEqual(d["payload"]["method"], "create")

    def test_missing_required_fields(self):
        d = issues.build_draft(cfg(), self.t, {"repo_name": "x"}, META_OK, existing_issues=[])
        self.assertEqual(d["status"], "incomplete")
        self.assertIn("Contributors", d["missing"])
        self.assertIn("Titel", d["missing"])

    def test_invalid_dropdown_and_unknown_field(self):
        d = issues.build_draft(cfg(), self.t, {**ANSWERS, "visibility": "secret", "eget": "x"}, META_OK)
        self.assertEqual(d["status"], "incomplete")
        self.assertTrue(any("secret" in e for e in d["errors"]))
        self.assertTrue(any("eget" in e for e in d["errors"]))

    def test_labels_must_exist_and_be_verified(self):
        meta = {**META_OK, "labels_existing": ["automation"], "labels_missing": ["create-repo"]}
        self.assertEqual(issues.build_draft(cfg(), self.t, ANSWERS, meta)["status"], "incomplete")
        self.assertEqual(issues.build_draft(cfg(), self.t, ANSWERS, None)["status"], "incomplete")

    def test_assignees_and_milestone(self):
        d = issues.build_draft(cfg(), self.t, ANSWERS, {**META_OK, "assignable": ["anna"]}, "anna,okand")
        self.assertEqual(d["payload"]["assignees"], ["anna"])
        self.assertEqual(issues.build_draft(cfg(milestone="Hösten"), self.t, ANSWERS, META_OK)["payload"]["milestone"], 2)
        self.assertEqual(issues.build_draft(cfg(milestone="X"), self.t, ANSWERS, META_OK)["status"], "incomplete")

    def test_markdown_sections_keep_structure(self):
        t = issues.parse_template(MD_TEXT, ".github/ISSUE_TEMPLATE/nytt.md")
        c = cfg(template_path=".github/ISSUE_TEMPLATE/nytt.md")
        d = issues.build_draft(c, t, {"title": "webshop", "Repository-namn": "webshop", "Contributors": "anna"}, META_OK)
        self.assertEqual(d["payload"]["body"], "## Repository-namn\n\nwebshop\n\n## Contributors\n\nanna")
        bad = issues.build_draft(c, t, {"title": "x", "body": "## Något helt annat"}, META_OK)
        self.assertEqual(bad["status"], "incomplete")


class TestDuplicates(Home):
    """Dubbla inbjudningar upptäcks mot befintliga issues på GitHub (inget sparas lokalt)."""

    def setUp(self):
        super().setUp()
        self.t = issues.parse_template((FIX / "invite_form.yml").read_text(encoding="utf-8"), FORM_PATH)
        self.answers = {"name": "Anna Andersson", "github_username": "anna-a", "level": "Junior",
                        "title": "Anna Andersson"}
        self.meta = {"labels_existing": ["invite-candidate"]}

    def existing(self, state):
        body = "### Namn\n\nAnna A\n\n### GitHub-användarnamn\n\nANNA-A\n\n### Nivå\n\nSenior"
        return {"issues": [{"number": 5, "body": body, "state": state}]}

    def test_open_duplicate_blocks(self):
        d = issues.build_draft(cfg(), self.t, self.answers, self.meta, existing_issues=self.existing("OPEN"))
        self.assertEqual(d["status"], "incomplete")
        self.assertTrue(any("redan en öppen inbjudan" in e and "#5" in e for e in d["errors"]))

    def test_closed_duplicate_warns(self):
        d = issues.build_draft(cfg(), self.t, self.answers, self.meta, existing_issues=self.existing("CLOSED"))
        self.assertEqual(d["status"], "ready")
        self.assertTrue(any("tidigare" in w for w in d["warnings"]))

    def test_unchecked_duplicates_warns(self):
        d = issues.build_draft(cfg(), self.t, self.answers, self.meta)
        self.assertEqual(d["status"], "ready")
        self.assertTrue(any("inte kontrollerat" in w for w in d["warnings"]))


# ---------------------------------------------------------------------------
class TestConfigAndGuard(Home):
    def test_unconfigured_is_blocked(self):
        code, out, _ = self.cli("issue", "config")
        self.assertEqual(code, 3)
        self.assertIn("Inget repository är konfigurerat", out)
        self.assertEqual(issues.check_issue_write({"method": "create", "owner": "a", "repo": "b"})[0], "deny")

    def test_configure_via_cli(self):
        code, out, _ = self.cli("issue", "configure", "--repository", "https://github.com/MinOrg/repo-flode",
                                "--template-path", FORM_PATH, "--enable")
        self.assertEqual(code, 0, out)
        self.assertEqual(issues.load_config()["repository"], "MinOrg/repo-flode")
        self.cli("issue", "configure", "--disable")
        self.assertFalse(issues.load_config()["enabled"])

    def test_guard(self):
        p = self.payload()
        decision, reason = issues.check_issue_write(dict(p))
        self.assertEqual(decision, "ask")
        self.assertIn("minorg/repo-flode", reason)
        self.assertEqual(issues.check_issue_write(dict(p, owner="MINORG"))[0], "ask")
        self.assertEqual(issues.check_issue_write(dict(p, repo="annat"))[0], "deny")
        self.assertEqual(issues.check_issue_write(dict(p, method="update", issue_number=1))[0], "deny")
        self.assertEqual(issues.check_issue_write(dict(p, body=""))[0], "deny")
        self.configure(enabled=False)
        self.assertEqual(issues.check_issue_write(dict(p))[0], "deny")

    def test_hook_script(self):
        p = self.payload()
        script = ROOT / ".claude" / "hooks" / "issue_guard.py"
        env = {**os.environ, "CLAUDE_PROJECT_DIR": str(ROOT)}

        def run(payload, raw=None):
            stdin = raw if raw is not None else json.dumps(
                {"tool_name": "mcp__github__issue_write", "tool_input": payload})
            r = subprocess.run([sys.executable, str(script), "pre"], input=stdin,
                               capture_output=True, text=True, env=env, timeout=30)
            return json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"]

        self.assertEqual(run(p), "ask")
        self.assertEqual(run(dict(p, repo="annat")), "deny")
        self.assertEqual(run(None, raw="inte json"), "deny")
        self.assertEqual(list(self.home.glob("**/*draft*")), [])  # inget sparas

    def test_cli_draft_flow_via_stdin(self):
        self.configure()
        data = {"template": FORM_TEXT, "answers": {"repo_name": "webshop"}, "meta": META_OK,
                "existing_issues": {"issues": []}}
        code, out, _ = self.cli("issue", "draft", stdin=json.dumps(data))
        self.assertEqual(code, 3)
        self.assertIn("Uppgifter som saknas", out)

        data["answers"] = ANSWERS
        code, out, _ = self.cli("issue", "draft", stdin=json.dumps(data))
        self.assertEqual(code, 0, out)
        self.assertIn("Vill du att jag skapar denna issue?", out)
        payload = json.loads(out.split("```json\n")[1].split("\n```")[0])
        self.assertEqual(issues.check_issue_write(payload)[0], "ask")

        code, out, _ = self.cli("issue", "questions", stdin=FORM_TEXT)
        self.assertIn("1. **Repository-namn** (**obligatorisk**)", out)
        code, out, _ = self.cli("issue", "template", stdin=FORM_TEXT)
        self.assertEqual(json.loads(out)["questions"][0]["key"], "repo_name")
        self.assertEqual(sorted(p.name for p in self.home.iterdir()), ["issue-config.json"])


if __name__ == "__main__":
    unittest.main()
