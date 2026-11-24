import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hooks"))
import guard  # noqa: E402


class TestDecide(unittest.TestCase):
    def test_deny_shortcuts(self):
        for c in ["gh issue close 12", "gh issue reopen 3 -R a/b", "gh project item-edit --id X",
                  "gh api graphql -f query='mutation{updateProjectV2ItemFieldValue(...)}'"]:
            self.assertEqual(guard.decide(c)[0], "deny", c)

    def test_ask_on_approve(self):
        self.assertEqual(guard.decide('python "C:/p/scripts/omi.py" move 12 Approved')[0], "ask")
        self.assertEqual(guard.decide('python /p/scripts/omi.py move #12 "Approved"')[0], "ask")
        self.assertEqual(guard.decide("python omi.py apply .omi/plans/a.json --approve")[0], "ask")

    def test_allow_normal(self):
        for c in ["python omi.py move 12 Done", "gh issue view 3", "gh pr create --fill", "git status"]:
            self.assertIsNone(guard.decide(c), c)


class TestSession(unittest.TestCase):
    def test_prints_one_line_cli_and_hint(self):
        t = guard.session_text(Path("/plug"), Path("/nonexistent-repo"))
        self.assertTrue(t.startswith("OMI_CLI: python"))
        self.assertIn("scripts", t)
        self.assertIn("init", t)
        self.assertEqual(len(t.splitlines()), 1)

    def test_reloads_task_context_after_clear(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d) / ".omi" / "tmp"
            tmp.mkdir(parents=True)
            (Path(d) / ".omi" / "project.json").write_text("{}", encoding="utf-8")
            (tmp / "current").write_text("7", encoding="utf-8")
            calls = []

            def fake(args, cwd):
                calls.append(args[-2:])
                return "# #7 [Task] Làm form đăng nhập"

            t = guard.session_text(Path("/plug"), Path(d), "clear", fake)
            self.assertIn("omi-resume", t)
            self.assertIn("# #7 [Task]", t)
            self.assertEqual(calls[0][-1], "resume")
            (tmp / "current").unlink()
            self.assertIn("NEXT: #8", guard.session_text(Path("/plug"), Path(d), "clear", lambda a, c: "#8 [Task] Y"))
            self.assertEqual(len(guard.session_text(Path("/plug"), Path(d), "resume", fake).splitlines()), 1)


if __name__ == "__main__":
    unittest.main()
