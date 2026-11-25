"""Tester för att skapa issues från den konfigurerade templaten.

Kör: python3 -m unittest discover -s tests -v
"""

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

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

    def cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def make_draft(self, answers=None, **kw):
        self.configure(**kw)
        t = issues.parse_template(FORM_TEXT, FORM_PATH)
        d = issues.build_draft(issues.load_config(), t, answers or ANSWERS, META_OK)
        self.assertEqual(d["status"], "draft", d)
        issues.save_draft(d)
        return d


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
        self.assertEqual(t["kind"], "form")
        self.assertEqual(t["labels"], ["create-repo", "automation"])
        self.assertEqual(t["assignees"], ["oscar-admin"])
        q = {x["key"]: x for x in issues.questions(t)}
        self.assertEqual(list(q), ["repo_name", "contributors", "visibility", "notes", "terms"])
        self.assertTrue(q["repo_name"]["required"])
        self.assertTrue(q["terms"]["required"])
        self.assertFalse(q["notes"]["required"])
        self.assertEqual(q["visibility"]["options"], ["private", "public"])

    def test_markdown(self):
        t = issues.parse_template(MD_TEXT, ".github/ISSUE_TEMPLATE/nytt.md")
        self.assertEqual(t["kind"], "markdown")
        self.assertEqual(t["labels"], ["create-repo", "automation"])
        self.assertEqual(t["assignees"], [])
        self.assertEqual(t["headings"], ["Repository-namn", "Contributors"])

    def test_invalid_form(self):
        with self.assertRaises(MonitorError):
            issues.parse_template("name: x\n", FORM_PATH)


# ---------------------------------------------------------------------------
class TestDraft(unittest.TestCase):
    def setUp(self):
        self.t = issues.parse_template(FORM_TEXT, FORM_PATH)

    def test_body_follows_github_issue_form_format(self):
        d = issues.build_draft(cfg(), self.t, ANSWERS, META_OK)
        self.assertEqual(d["status"], "draft")
        self.assertEqual(d["payload"]["body"], (
            "### Repository-namn\n\nwebshop\n\n"
            "### Contributors\n\nanna\nerik\n\n"
            "### Synlighet\n\nprivate\n\n"
            "### Övrigt\n\nInget\n\n"
            "### Bekräftelse\n\n- [X] Jag har kontrollerat användarnamnen\n- [ ] Skicka välkomstmail"
        ))
        self.assertEqual(d["payload"]["title"], "[Nytt repo]: webshop")
        self.assertEqual(d["payload"]["labels"], ["create-repo", "automation"])
        self.assertEqual(d["payload"]["assignees"], ["oscar-admin"])
        self.assertEqual(d["payload"]["owner"], "minorg")
        self.assertEqual(d["payload"]["method"], "create")

    def test_missing_required_fields_become_questions(self):
        d = issues.build_draft(cfg(), self.t, {"repo_name": "x"}, META_OK)
        self.assertEqual(d["status"], "incomplete")
        self.assertIn("Contributors", d["missing"])
        self.assertIn("Bekräftelse: Jag har kontrollerat användarnamnen", d["missing"])
        self.assertIn("Titel", d["missing"])

    def test_invalid_dropdown_and_unknown_field(self):
        d = issues.build_draft(cfg(), self.t, {**ANSWERS, "visibility": "secret", "eget": "x"}, META_OK)
        self.assertEqual(d["status"], "incomplete")
        self.assertTrue(any("secret" in e for e in d["errors"]))
        self.assertTrue(any("eget" in e for e in d["errors"]))

    def test_missing_label_blocks_draft(self):
        meta = {**META_OK, "labels_existing": ["automation"], "labels_missing": ["create-repo"]}
        d = issues.build_draft(cfg(), self.t, ANSWERS, meta)
        self.assertEqual(d["status"], "incomplete")
        self.assertTrue(any("create-repo" in e for e in d["errors"]))

    def test_unverified_labels_block_draft(self):
        d = issues.build_draft(cfg(), self.t, ANSWERS, None)
        self.assertEqual(d["status"], "incomplete")

    def test_assignees_filtered_and_unverified(self):
        meta = {**META_OK, "assignable": ["anna"]}
        d = issues.build_draft(cfg(), self.t, ANSWERS, meta, "anna,okand")
        self.assertEqual(d["payload"]["assignees"], ["anna"])
        self.assertTrue(any("oscar-admin" in w and "okand" in w for w in d["warnings"]))
        d = issues.build_draft(cfg(), self.t, ANSWERS, {**META_OK, "assignable": None})
        self.assertNotIn("assignees", d["payload"])
        self.assertEqual(d["status"], "draft")

    def test_milestone(self):
        d = issues.build_draft(cfg(milestone="Hösten"), self.t, ANSWERS, META_OK)
        self.assertEqual(d["payload"]["milestone"], 2)
        d = issues.build_draft(cfg(milestone="Finns inte"), self.t, ANSWERS, META_OK)
        self.assertEqual(d["status"], "incomplete")

    def test_configured_fixed_title_and_extra_labels(self):
        d = issues.build_draft(cfg(title="Skapa repo", extra_labels=["automation"]), self.t,
                               {k: v for k, v in ANSWERS.items() if k != "title"}, META_OK)
        self.assertEqual(d["payload"]["title"], "Skapa repo")
        self.assertEqual(d["payload"]["labels"], ["create-repo", "automation"])

    def test_markdown_sections_keep_structure(self):
        t = issues.parse_template(MD_TEXT, ".github/ISSUE_TEMPLATE/nytt.md")
        c = cfg(template_path=".github/ISSUE_TEMPLATE/nytt.md")
        d = issues.build_draft(c, t, {"title": "webshop", "Repository-namn": "webshop",
                                      "Contributors": "anna"}, META_OK)
        self.assertEqual(d["status"], "draft")
        self.assertEqual(d["payload"]["body"], "## Repository-namn\n\nwebshop\n\n## Contributors\n\nanna")
        self.assertEqual(d["payload"]["title"], "Nytt repo: webshop")
        bad = issues.build_draft(c, t, {"title": "x", "body": "## Något helt annat"}, META_OK)
        self.assertEqual(bad["status"], "incomplete")


# ---------------------------------------------------------------------------
class TestConfigAndGuard(Home):
    def test_unconfigured_is_blocked(self):
        code, out, _ = self.cli("issue", "config")
        self.assertEqual(code, 3)
        self.assertIn("Inget repository är konfigurerat", out)
        decision, reason = issues.check_issue_write({"method": "create", "owner": "a", "repo": "b"})
        self.assertEqual(decision, "deny")
        self.assertIn("inte konfigurerad", reason)

    def test_configure_via_cli(self):
        code, out, _ = self.cli("issue", "configure", "--repository", "https://github.com/MinOrg/repo-flode",
                                "--template-path", FORM_PATH, "--labels", "extra", "--enable")
        self.assertEqual(code, 0, out)
        c = issues.load_config()
        self.assertEqual(c["repository"], "MinOrg/repo-flode")
        self.assertEqual(c["extra_labels"], ["extra"])
        self.assertTrue(c["enabled"])
        self.cli("issue", "configure", "--disable")
        self.assertFalse(issues.load_config()["enabled"])

    def test_guard_allows_only_exact_draft_and_asks(self):
        d = self.make_draft()
        decision, reason = issues.check_issue_write(dict(d["payload"]))
        self.assertEqual(decision, "ask")
        self.assertIn("minorg/repo-flode", reason)
        # Ordning på labels och skiftläge på owner spelar ingen roll
        p = dict(d["payload"], labels=list(reversed(d["payload"]["labels"])), owner="MINORG")
        self.assertEqual(issues.check_issue_write(p)[0], "ask")

    def test_guard_denies_other_repo_update_and_changed_content(self):
        d = self.make_draft()
        p = d["payload"]
        self.assertEqual(issues.check_issue_write(dict(p, repo="annat"))[0], "deny")
        self.assertEqual(issues.check_issue_write(dict(p, method="update", issue_number=1))[0], "deny")
        self.assertEqual(issues.check_issue_write(dict(p, body=p["body"] + "\nextra"))[0], "deny")
        self.assertEqual(issues.check_issue_write(dict(p, labels=["annan"]))[0], "deny")
        self.configure(enabled=False)
        self.assertEqual(issues.check_issue_write(dict(p))[0], "deny")

    def test_post_hook_records_and_prevents_duplicates(self):
        d = self.make_draft()
        resp = {"content": [{"type": "text", "text": json.dumps(
            {"url": "https://github.com/minorg/repo-flode/issues/42"})}]}
        rec = issues.record_created(dict(d["payload"]), resp)
        self.assertEqual(rec["issue_number"], 42)
        decision, reason = issues.check_issue_write(dict(d["payload"]))
        self.assertEqual(decision, "deny")
        self.assertIn("redan skapad", reason)
        code, out, _ = self.cli("issue", "list")
        self.assertIn("issues/42", out)

    def test_hook_script_end_to_end(self):
        d = self.make_draft()
        script = ROOT / ".claude" / "hooks" / "issue_guard.py"
        env = {**os.environ, "CLAUDE_PROJECT_DIR": str(ROOT)}

        def run(mode, payload, response=None):
            event = {"tool_name": "mcp__github__issue_write", "tool_input": payload}
            if response is not None:
                event["tool_response"] = response
            r = subprocess.run([sys.executable, str(script), mode], input=json.dumps(event),
                               capture_output=True, text=True, env=env, timeout=30)
            return r

        r = run("pre", d["payload"])
        self.assertEqual(json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"], "ask")
        r = run("pre", dict(d["payload"], repo="annat"))
        self.assertEqual(json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"], "deny")
        run("post", d["payload"], "Created https://github.com/minorg/repo-flode/issues/7")
        r = run("pre", d["payload"])
        self.assertEqual(json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"], "deny")
        # Trasig indata => neka
        r = subprocess.run([sys.executable, str(script), "pre"], input="inte json",
                           capture_output=True, text=True, env=env, timeout=30)
        self.assertEqual(json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_cli_draft_flow(self):
        self.configure()
        work = self.home / "work"
        work.mkdir()
        (work / "template.yml").write_text(FORM_TEXT, encoding="utf-8")
        (work / "answers.json").write_text(json.dumps({"repo_name": "webshop"}), encoding="utf-8")
        (work / "meta.json").write_text(json.dumps(META_OK), encoding="utf-8")
        args = ["issue", "draft", "--template-file", str(work / "template.yml"),
                "--answers", str(work / "answers.json"), "--repo-meta", str(work / "meta.json")]
        code, out, _ = self.cli(*args)
        self.assertEqual(code, 3)
        self.assertIn("Uppgifter som saknas", out)
        self.assertIn("inte klart", out)

        (work / "answers.json").write_text(json.dumps(ANSWERS), encoding="utf-8")
        code, out, _ = self.cli(*args)
        self.assertEqual(code, 0, out)
        self.assertIn("Vill du att jag skapar denna issue?", out)
        self.assertIn("**Repository:** minorg/repo-flode", out)
        self.assertIn("Nytt projekt-repo", out)
        draft_id = out.split("Utkast-id: `")[1].split("`")[0]
        code, out, _ = self.cli("issue", "payload", draft_id)
        payload = json.loads(out)
        self.assertEqual(issues.check_issue_write(payload)[0], "ask")

        code, out, _ = self.cli("issue", "template", str(work / "template.yml"))
        self.assertEqual(json.loads(out)["questions"][0]["key"], "repo_name")


if __name__ == "__main__":
    unittest.main()
