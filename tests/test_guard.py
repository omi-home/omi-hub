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

    def test_ac137_2_ask_on_raw_issue_project_ops_with_hint(self):
        for c, hint in [("gh issue create -t x -b y", "OMI_CLI new"), ("gh issue edit 3 --body-file f", "OMI_CLI edit"),
                        ("gh issue comment 3 --edit-last --body x", "OMI_CLI edit"),
                        ("gh issue delete 3 --yes", "Cancelled"), ("gh issue transfer 3 o/r", "Cancelled"),
                        ("gh project item-add 8 --owner o --url u", "audit --fix"),
                        ("gh project item-delete 8 --id X", "OMI_CLI"), ("gh project item-archive 8 --id X", "OMI_CLI"),
                        ("gh project field-create 8 --name F", "OMI_CLI init"),
                        ("gh api graphql -f query='mutation{addProjectV2ItemById(input:{})}'", "OMI_CLI new"),
                        ("gh api graphql -f query='mutation{deleteProjectV2Item(input:{})}'", "audit --fix"),
                        ("gh api graphql -f query='mutation{addSubIssue(input:{})}'", "--parent"),
                        ("gh api graphql -f query='mutation{addBlockedBy(input:{})}'", "block <n> --by")]:
            d = guard.decide(c)
            self.assertEqual(d[0], "ask", c)
            self.assertIn(hint, d[1], c)

    def test_ac137_3_text_in_heredoc_or_body_not_matched(self):
        for c in ["python omi.py new Task \"x\" --body \"chạy gh issue create rồi gh project item-edit\"",
                  "gh pr create --title t -b 'không dùng gh issue edit hay addSubIssue'",
                  "git commit -F - <<'EOF'\nghi chú: gh issue close 3, gh project item-add\nEOF",
                  "cat > note.md <<EOF\naddBlockedBy updateProjectV2ItemFieldValue\nEOF\ngit status",
                  "git commit -m @'\ngh issue create và gh issue reopen\n'@"]:
            self.assertIsNone(guard.decide(c), c)
        self.assertEqual(guard.decide("cat <<EOF > a\nx\nEOF\ngh issue create -t a")[0], "ask")  # lệnh sau heredoc vẫn bắt

    def test_bug164_body_flag_only_at_token_start(self):
        self.assertEqual(guard.command_part("x --body 'a' y"), "x --body y")
        for c in ("web-b gh issue create", "XS-b gh issue create"):  # -b giữa token không phải cờ
            self.assertEqual(guard.command_part(c), c)

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
            self.assertEqual(len(guard.session_text(Path("/plug"), Path(d), "resume", fake).splitlines()), 2)

    def test_ac137_1_session_prints_omi_cli_rule_when_init(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / ".omi").mkdir()
            (Path(d) / ".omi" / "project.json").write_text("{}", encoding="utf-8")
            t = guard.session_text(Path("/plug"), Path(d), "resume")
            self.assertRegex(t, r"QUY TẮC: issue/GitHub Project chỉ thao tác qua OMI_CLI.*báo người dùng.*issue omi-hub")
        self.assertNotIn("QUY TẮC", guard.session_text(Path("/plug"), Path("/nonexistent-repo")))


if __name__ == "__main__":
    unittest.main()
