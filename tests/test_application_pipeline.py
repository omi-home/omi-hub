import os
import re
import time
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from support import WF
from test_application_items import FakeGh
from omi_hub.application import items, pipeline, views
from omi_hub.domain.errors import RuleError


class PipelineGh(FakeGh):
    def __init__(self):
        super().__init__()
        self.files, self.developed, self.branches = [], [], {}
        self.branch_prs, self.link_lag, self.created, self.pending = {}, 0, 0, {}

    def merge_pr(self, cfg, pr):
        for i in self.issues.values():
            for p in i["prs"]:
                if p["number"] == pr:
                    p.update(state="MERGED", merged=True)

    def pr_checks(self, cfg, pr):
        return None, ""  # sandbox giả: không có CI → qa chạy commands.test

    def open_pr_for_branch(self, cfg, head):
        return self.branch_prs.get(head)

    def issue_snapshot(self, cfg, n):
        if self.link_lag and n in self.pending:  # GitHub liên kết PR vào issue trễ vài lần đọc
            self.link_lag -= 1
            if not self.link_lag:
                self.issues[n]["prs"].append(dict(self.pending.pop(n)))
        return super().issue_snapshot(cfg, n)

    def create_pr(self, cfg, title, body, head):
        n = int(re.search(r"Closes #(\d+)", body).group(1))
        self.created += 1
        if self.link_lag:
            self.pending = {n: {"number": 50, "state": "OPEN", "merged": False}}
        else:
            self.issues[n]["prs"].append({"number": 50, "state": "OPEN", "merged": False})
        self.pr_created = (title, body)
        return 50

    def pr_files(self, cfg, pr):
        return self.files

    def pr_diff(self, cfg, pr):
        return "+x = 1"

    def issue_branches(self, cfg, n):
        return self.branches.get(n, [])

    def develop(self, cfg, n, cwd=None):
        self.developed.append(n)


PCFG = {"commands": {"test": "T", "accept": "A {n}"}, "review_max_diff_lines": 100}
OPEN_PR = {"number": 50, "state": "OPEN", "merged": False}
MERGED_PR = [{"number": 99, "state": "MERGED", "merged": True}]
AC1 = "### Acceptance criteria\n- [ ] đăng nhập được"


class TestPipeline(unittest.TestCase):
    def setUp(self):
        self.g = PipelineGh()
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = dict(PCFG, _root=self.tmp.name)
        self.T = Path(self.tmp.name) / ".omi" / "tmp"
        self.patches = [mock.patch.object(items, "gh", self.g), mock.patch.object(pipeline, "gh", self.g),
                        mock.patch.object(pipeline.handoff, "handoff")]  # handoff có test riêng
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def st(self, n):
        return self.g.issues[n]["status"]

    def test_start_moves_draft_to_in_progress_and_checks_out(self):
        self.g.add(2, "User Story", "Approved")
        self.g.add(3, "Task", "Draft", parent=2)
        self.assertEqual(pipeline.start(self.cfg, WF, 3), 3)
        self.assertEqual(self.st(3), "In Progress")
        self.assertEqual(self.g.developed, [3])
        self.assertEqual((self.T / "current").read_text(encoding="utf-8"), "3")

    def docs_setup(self, task_refs, story_refs):
        d = Path(self.tmp.name) / "docs"
        d.mkdir()
        (d / "spec.md").write_text("# Spec\n## Outbox\nghi outbox cùng transaction\n### Chi tiết\nbảng outbox\n"
                                   "## Auth\nJWT ES256\n## Khác\nkhông lấy\n", encoding="utf-8")
        self.g.add(2, "User Story", "In Progress", body=AC1 + "\n\n### Tham chiếu\n" + story_refs)
        self.g.add(3, "Task", "In Progress", parent=2, body="### Việc cần làm\nx\n\n### Tham chiếu\n" + task_refs)

    def test_ac109_1_context_includes_referenced_sections_only(self):
        self.docs_setup("- docs/spec.md#outbox", "- docs/spec.md#auth\n- docs/spec.md#outbox")
        with mock.patch("builtins.print"):
            text = pipeline.context(self.cfg, 3)
        self.assertIn("## Tham chiếu docs/spec.md#outbox\n## Outbox\nghi outbox cùng transaction\n### Chi tiết\nbảng outbox", text)
        self.assertIn("## Tham chiếu docs/spec.md#auth\n## Auth\nJWT ES256", text)
        self.assertEqual(text.count("## Tham chiếu docs/spec.md#outbox"), 1)  # task và parent trùng → một lần
        self.assertNotIn("không lấy", text)

    def test_ac109_2_context_warns_on_missing_reference(self):
        self.docs_setup("- docs/spec.md#khong-co\n- docs/nope.md#a\n- ../ngoai-repo.md", "- docs/spec.md#auth")
        with mock.patch("builtins.print"):
            text = pipeline.context(self.cfg, 3)
        for ref in ("docs/spec.md#khong-co", "docs/nope.md#a", "../ngoai-repo.md"):
            self.assertIn(f"⚠️ Tham chiếu không tìm thấy: {ref}", text)
        self.assertIn("JWT ES256", text)  # tham chiếu hợp lệ vẫn được ghép

    def test_start_draft_with_open_blocker_stops_at_waiting(self):
        self.g.add(2, "User Story", "Approved")
        self.g.add(3, "Task", "Draft", parent=2)
        self.g.add(4, "Task", "Ready", parent=2)
        self.g.blockers = {3: [4]}
        with self.assertRaisesRegex(RuleError, "đang ở 'Waiting'"):
            pipeline.start(self.cfg, WF, 3)
        self.assertEqual((self.st(3), self.g.developed), ("Waiting", []))

    def test_submit_first_time_requests_review_with_security(self):
        self.g.add(2, "User Story", "In Progress", body=AC1)
        self.g.add(3, "Task", "In Progress", parent=2)
        def fake_run(cmd, cwd=None):
            cmd = " ".join(cmd) if isinstance(cmd, list) else cmd
            if cmd.startswith("git diff"):
                return 0, "src/auth/login.py\n"
            if cmd.startswith("git log"):
                return 0, "#3: thêm login\n"
            return 0, "omi/3-login"

        with mock.patch.object(pipeline, "run_cmd", side_effect=fake_run):
            pr, reviewers = pipeline.submit(self.cfg, WF, 3)
        self.assertEqual((pr, reviewers, self.st(3)), (50, ["code", "security"], "In Review"))
        title, body = self.g.pr_created
        self.assertEqual(title, "#3 (#3)")
        self.assertIn("Closes #3", body)
        self.assertIn("- #3: thêm login", body)
        self.assertIn("Có chạm security", body)
        self.assertIn("+x = 1", (self.T / "review-3.md").read_text(encoding="utf-8"))
        self.assertFalse(any("omi:reviewed" in c for c in self.g.notes.get(3, [])))  # marker do review-done ghi

    def _pack126(self):
        self.g.add(2, "Functional Requirement", "In Progress", body=AC1)
        self.g.add(3, "Task", "In Progress", parent=2)
        self.g.add(4, "Task", "Ready", parent=2)
        self.g.add(5, "Task", "Done", parent=2, state="CLOSED")
        self.g.notes[2] = ["<!-- omi:findings -->\n\n- [ ] Tách hàm (từ #4)"]
        self.g.pr_diff = lambda cfg, pr: "\n".join([
            "diff --git a/src/a.py b/src/a.py", "+x = 1",
            "diff --git a/package-lock.json b/package-lock.json", *["+lock"] * 50,
            "diff --git a/web/pnpm-lock.yaml b/web/pnpm-lock.yaml", "+y"])
        with mock.patch.object(pipeline, "run_cmd", return_value=(1, "boom\nAssertionError: x")), \
                mock.patch("builtins.print"):
            pipeline.check(dict(self.cfg, commands={"test": "T"}))

        def fake_run(cmd, cwd=None):
            cmd = " ".join(cmd) if isinstance(cmd, list) else cmd
            return (0, "#3: thêm login\n#3: sửa test\n") if cmd.startswith("git log") else (0, "omi/3-x")
        with mock.patch.object(pipeline, "run_cmd", side_effect=fake_run), mock.patch("builtins.print"):
            pipeline.submit(self.cfg, WF, 3)
        return (self.T / "review-3.md").read_text(encoding="utf-8")

    def test_ac126_1_pack_has_commits_and_last_check(self):
        pack = self._pack126()
        self.assertIn("## Commit\n- #3: thêm login\n- #3: sửa test", pack)
        self.assertIn("## Check gần nhất\nCHECK FAIL (test)\nboom\nAssertionError: x", pack)

    def test_ac126_2_pack_has_open_siblings_and_findings(self):
        pack = self._pack126()
        self.assertIn("## Task anh em còn mở\n- #4 #4 — Ready", pack)
        self.assertNotIn("- #5 ", pack)
        self.assertIn("- [2.1] Tách hàm (từ #4)", pack)

    def test_ac126_3_pack_diff_drops_lockfiles(self):
        pack = self._pack126()
        self.assertIn("## Diff PR #50 (2 dòng)\nĐã bỏ file sinh/lockfile: package-lock.json, web/pnpm-lock.yaml",
                      pack)  # giới hạn dòng tính trên phần còn lại
        self.assertNotIn("+lock", pack)

    def test_ac63_1_submit_waits_for_pr_link(self):
        self.g.add(2, "User Story", "In Progress")
        self.g.add(3, "Task", "In Progress", parent=2)
        self.g.link_lag = 3
        with mock.patch.object(pipeline, "run_cmd", return_value=(0, "omi/3-x")),                 mock.patch.object(pipeline.time, "sleep") as sl:
            pipeline.submit(self.cfg, WF, 3)
        self.assertEqual((self.st(3), self.g.created), ("In Review", 1))
        self.assertGreater(sl.call_count, 1)

    def test_ac63_1_submit_rerun_no_duplicate_pr(self):
        self.g.add(2, "User Story", "In Progress")
        self.g.add(3, "Task", "In Progress", parent=2)
        self.g.branch_prs["omi/3-x"] = 50  # PR đã tạo ở lần trước, issue chưa liên kết
        self.g.link_lag, self.g.pending = 1, {3: {"number": 50, "state": "OPEN", "merged": False}}
        with mock.patch.object(pipeline, "run_cmd", return_value=(0, "omi/3-x")),                 mock.patch.object(pipeline.time, "sleep"):
            self.assertEqual(pipeline.submit(self.cfg, WF, 3)[0], 50)
        self.assertEqual((self.st(3), self.g.created), ("In Review", 0))

    def test_submit_gives_up_when_never_linked(self):
        self.g.add(2, "User Story", "In Progress")
        self.g.add(3, "Task", "In Progress", parent=2)
        self.g.link_lag = 99
        with mock.patch.object(pipeline, "run_cmd", return_value=(0, "omi/3-x")),                 mock.patch.object(pipeline.time, "sleep"):
            with self.assertRaisesRegex(RuleError, "chạy lại `submit 3`"):
                pipeline.submit(self.cfg, WF, 3)
        self.assertEqual(self.st(3), "In Progress")

    def test_submit_after_rework_skips_review(self):
        self.g.add(2, "User Story", "In Progress")
        self.g.add(3, "Task", "In Progress", parent=2, prs=[dict(OPEN_PR)])
        self.g.notes[3] = ["<!-- omi:reviewed -->"]
        with mock.patch.object(pipeline, "run_cmd", return_value=(0, "3-x")):
            self.assertEqual(pipeline.submit(self.cfg, WF, 3), (50, []))
        self.assertEqual(self.st(3), "In Review")

    def test_bug191_submit_rejects_wrong_branch_or_foreign_closing_commit(self):
        self.g.add(2, "Functional Requirement", "In Progress")
        self.g.add(232, "Task", "In Progress", parent=2)
        self.g.add(388, "Task", "In Progress", parent=2)

        def git(head, msgs=""):
            def run(cmd, cwd=None):
                assert cmd[:2] != ["git", "push"], "không được push"
                return 0, msgs if cmd[:2] == ["git", "log"] else head
            return run
        for head in ("388-ui-date", "omi/2320-x", "main"):
            with mock.patch.object(pipeline, "run_cmd", side_effect=git(head)):
                with self.assertRaisesRegex(RuleError, f"'{head}' không phải nhánh của #232"):
                    pipeline.submit(self.cfg, WF, 232)
        self.g.branches[232] = ["feature/date"]  # nhánh liên kết bằng gh issue develop, tên tuỳ ý
        with mock.patch.object(pipeline, "run_cmd", side_effect=git("feature/date", "#232: x\n\nCloses #388\nFixes #232")):
            with self.assertRaisesRegex(RuleError, "đóng issue khác: #388"):
                pipeline.submit(self.cfg, WF, 232)
        self.assertEqual((self.st(232), self.st(388), self.g.created), ("In Progress", "In Progress", 0))

    def test_ac132_1_check_warns_without_test_cmd(self):
        with mock.patch.object(pipeline, "run_cmd", return_value=(0, "")), mock.patch("builtins.print") as pr:
            self.assertEqual(pipeline.check(dict(self.cfg, commands={"lint": "L"})), 0)
        pr.assert_called_once_with("CHECK WARN: chưa cấu hình commands.test")

    def test_ac132_3_submit_first_time_prints_one_review_line(self):
        self.g.add(2, "Functional Requirement", "In Progress")
        self.g.add(3, "Task", "In Progress", parent=2)
        self.g.link_lag = 2
        with mock.patch.object(pipeline, "run_cmd", return_value=(0, "omi/3-x")), \
                mock.patch.object(pipeline.time, "sleep"), mock.patch("builtins.print") as pr:
            pipeline.submit(self.cfg, WF, 3)
        lines = [str(c.args[0]) for c in pr.call_args_list if c.args]
        self.assertEqual(len([x for x in lines if x.startswith("REVIEW #3 PR #50")]), 1, lines)

    def test_ac132_3_cli_stdout_line_buffered(self):
        from omi_hub.cli import main as cli
        out = mock.Mock()
        with mock.patch.object(cli.sys, "stdout", out), mock.patch.object(cli.sys, "stderr", mock.Mock()), \
                mock.patch.object(cli, "run", return_value=0):
            cli.main(["check"])
        out.reconfigure.assert_called_once_with(encoding="utf-8", line_buffering=True)

    def test_qa_pass_merges_done_and_accepts_parent(self):
        self.g.add(1, "Epic", "In Progress")
        self.g.add(2, "User Story", "In Progress", parent=1, body=AC1)
        self.g.add(3, "Task", "In Review", parent=2, prs=[dict(OPEN_PR)])
        self.g.notes[3] = ["<!-- omi:reviewed -->"]
        with mock.patch.object(pipeline, "run_cmd", return_value=(0, "test_ac2_1 ... ok")):
            self.assertEqual(pipeline.qa(self.cfg, WF, 3), 0)
        self.assertEqual((self.st(3), self.st(2), self.st(1)), ("Done", "Done", "Done"))
        self.assertFalse((self.T / "current").exists())

    def test_qa_fail_reworks_and_writes_log(self):
        self.g.add(2, "User Story", "In Progress")
        self.g.add(3, "Task", "In Review", parent=2, prs=[dict(OPEN_PR)])
        self.g.notes[3] = ["<!-- omi:reviewed -->"]
        with mock.patch.object(pipeline, "run_cmd", return_value=(1, "AssertionError: boom")):
            self.assertEqual(pipeline.qa(self.cfg, WF, 3), 1)
        self.assertEqual((self.st(3), self.g.issues[3]["rework_count"]), ("In Progress", 1))
        self.assertIn("boom", (self.T / "qa-3.log").read_text(encoding="utf-8"))

    def test_ac132_2_qa_ci_infra_error_no_rework(self):
        self.g.add(2, "Functional Requirement", "In Progress")
        self.g.add(3, "Task", "In Review", parent=2, prs=[dict(OPEN_PR)])
        self.g.notes[3] = ["<!-- omi:reviewed -->"]
        for log in ("pr-lint\tfail\nError: Input required and not supplied: token",
                    "HTTP 502: Bad Gateway (https://api.github.com/graphql)"):
            self.g.pr_checks = lambda cfg, pr, log=log: (False, log)
            with mock.patch("builtins.print") as pr:
                self.assertEqual(pipeline.qa(self.cfg, WF, 3), 1)
            self.assertTrue(pr.call_args.args[0].startswith("QA INFRA "), pr.call_args)
            self.assertEqual((self.st(3), self.g.issues[3]["rework_count"]), ("In Review", 0))
        self.g.pr_checks = lambda cfg, pr: (False, "AssertionError: boom")  # lỗi task vẫn rework
        with mock.patch("builtins.print"):
            pipeline.qa(self.cfg, WF, 3)
        self.assertEqual((self.st(3), self.g.issues[3]["rework_count"]), ("In Progress", 1))

    def test_bug186_accept_runs_on_fresh_default_branch(self):
        self.g.add(2, "Functional Requirement", "In QA", body=AC1)
        calls = []
        def run(cmd, cwd=None):
            calls.append(cmd if isinstance(cmd, str) else " ".join(cmd))
            return 0, "test_ac2_1 ... ok"
        with mock.patch.object(pipeline, "run_cmd", side_effect=run), mock.patch("builtins.print"):
            self.assertEqual(pipeline.accept(dict(self.cfg, default_branch="develop"), WF, 2), 0)
        self.assertEqual(calls, ["git fetch origin develop", "git checkout develop",
                                 "git merge --ff-only origin/develop", "A 2"])
        self.g.issues[2]["status"] = "In QA"
        with mock.patch.object(pipeline, "run_cmd", return_value=(1, "local changes would be overwritten")):
            with self.assertRaisesRegex(RuleError, "Không cập nhật được nhánh main"):
                pipeline.accept(self.cfg, WF, 2)
        self.assertEqual(self.st(2), "In QA")  # không rework vì lỗi git

    def test_accept_manual_unticked_stays_in_qa(self):
        self.g.add(2, "User Story", "In QA", body="### Acceptance criteria\n- [ ] [manual] UI")
        self.assertEqual(pipeline.accept(self.cfg, WF, 2), 1)
        self.assertEqual((self.st(2), self.g.issues[2]["rework_count"]), ("In QA", 0))

    def test_accept_auto_fail_reworks(self):
        self.g.add(2, "User Story", "In QA", body=AC1)
        with mock.patch.object(pipeline, "run_cmd", return_value=(0, "nothing")):
            self.assertEqual(pipeline.accept(self.cfg, WF, 2), 1)
        self.assertEqual(self.st(2), "In Progress")

    def test_ac122_1_review_done_improve_appends_findings_to_parent(self):
        self.g.add(2, "Functional Requirement", "In Progress")
        self.g.add(3, "Task", "In Review", parent=2, prs=[dict(OPEN_PR)])
        n_issues = len(self.g.issues)
        with mock.patch("builtins.print"):
            pipeline.review_done(self.cfg, WF, 3, improve=["Tách hàm parse", "Đặt tên rõ hơn"])
            pipeline.review_done(self.cfg, WF, 3, improve=["tách hàm  parse", "Thêm log lỗi"])
        found = [c for c in self.g.notes[2] if "omi:findings" in c]
        self.assertEqual(len(found), 1)  # một comment, sửa tại chỗ
        self.assertIn("- [ ] Tách hàm parse (từ #3)\n- [ ] Đặt tên rõ hơn (từ #3)\n- [ ] Thêm log lỗi (từ #3)",
                      found[0])
        self.assertEqual(found[0].count("parse"), 1)
        self.assertEqual(len(self.g.issues), n_issues)  # không tạo issue mới

    def test_ac122_2_context_lists_open_findings_of_ancestors(self):
        self.g.add(1, "Epic", "In Progress")
        self.g.add(2, "Functional Requirement", "In Progress", parent=1)
        self.g.add(3, "Task", "In Progress", parent=2)
        self.g.notes[1] = ["<!-- omi:findings -->\n\n- [x] Đã làm (xong ở #9)\n- [ ] Dọn config (từ #8)"]
        self.g.notes[2] = ["<!-- omi:findings -->\n\n- [ ] Tách hàm parse (từ #4)"]
        with mock.patch("builtins.print"):
            text = pipeline.context(self.cfg, 3)
        self.assertIn("## Findings mang theo\n- [2.1] Tách hàm parse (từ #4)\n- [1.2] Dọn config (từ #8)", text)
        self.assertNotIn("Đã làm", text)

    def test_ac122_3_submit_findings_marks_done_or_rejects(self):
        self.g.add(1, "Epic", "In Progress")
        self.g.add(2, "Functional Requirement", "In Progress", parent=1)
        self.g.add(3, "Task", "In Progress", parent=2)
        self.g.notes[1] = ["<!-- omi:findings -->\n\n- [ ] Dọn config (từ #8)"]
        self.g.notes[2] = ["<!-- omi:findings -->\n\n- [ ] Tách hàm (từ #4)\n- [ ] Đặt tên (từ #4)"]
        before = {k: list(v) for k, v in self.g.notes.items()}
        def no_push(cmd, cwd=None):
            assert cmd[:2] != ["git", "push"], "không được push"
            return 0, "3-x"
        with mock.patch.object(pipeline, "run_cmd", side_effect=no_push):
            with self.assertRaisesRegex(RuleError, "2.9"):
                pipeline.submit(self.cfg, WF, 3, "2.1,2.9")
        self.assertEqual(self.g.notes, before)  # mã sai → không sửa gì
        with mock.patch("builtins.print"):
            pipeline.done_findings(self.cfg, self.g.issue_snapshot(self.cfg, 3), "2.2,1.1")
        self.assertIn("- [ ] Tách hàm (từ #4)\n- [x] Đặt tên (từ #4) (xong ở #3)", self.g.notes[2][0])
        self.assertIn("- [x] Dọn config (từ #8) (xong ở #3)", self.g.notes[1][0])

    def test_ac122_4_findings_escalate_then_epic_reports_open(self):
        self.g.add(1, "Epic", "In Progress")
        self.g.add(2, "Functional Requirement", "In Progress", parent=1)
        self.g.add(3, "Task", "In QA", parent=2, prs=MERGED_PR)
        self.g.notes[2] = ["<!-- omi:findings -->\n\n- [x] Đã làm (xong ở #5)\n- [ ] Tách hàm (từ #4)"]
        with mock.patch("builtins.print") as pr:
            items.move(self.cfg, WF, 3, "Done")  # FR → In QA: finding mở chuyển lên Epic
        self.assertIn("- [x] Tách hàm (từ #4) (chuyển lên #1)", self.g.notes[2][0])
        self.assertIn("- [ ] Tách hàm (từ #4) (chuyển từ #2)", self.g.notes[1][0])
        self.assertNotIn("Đã làm", self.g.notes[1][0])
        with mock.patch("builtins.print") as pr:
            items.move(self.cfg, WF, 2, "Done")  # FR Done → Epic Done, còn finding
        self.assertIn("FINDINGS OPEN #1 1", " ".join(str(c) for c in pr.call_args_list))
        self.g.issues[1]["milestone"] = "v1"
        with mock.patch.object(views, "gh", self.g):
            self.g.AUDIT_TITLE = "audit"
            self.g.project_items = lambda cfg: [dict(i, blockers=[]) for i in self.g.issues.values()]
            text = views.status(self.cfg, WF)
        self.assertIn("Findings:\n- [1.1] Tách hàm (từ #4) (chuyển từ #2) (Epic #1 đã xong)", text)

    def test_ac122_5_carry_draft_task_into_parent_finding(self):
        self.g.add(2, "Functional Requirement", "In Progress")
        self.g.add(5, "Task", "Draft", parent=2, body="### Việc cần làm\n- Tách hàm parse\n- Thêm test rỗng")
        self.g.add(6, "Task", "Ready", parent=2)
        with mock.patch("builtins.print"):
            pipeline.carry(self.cfg, WF, [5])
        self.assertEqual((self.st(5), self.g.issues[5]["state"]), ("Cancelled", "CLOSED"))
        self.assertIn("- [ ] #5: Tách hàm parse; Thêm test rỗng (từ #5)",
                      next(c for c in self.g.notes[2] if "omi:findings" in c))
        self.assertTrue(any("carry" in c for c in self.g.notes[5]))  # lý do Cancelled
        with self.assertRaisesRegex(RuleError, "Task Draft"):
            pipeline.carry(self.cfg, WF, [6])

    def test_ac126_4_review_done_override_passes_with_reason(self):
        self.g.add(2, "Functional Requirement", "In Progress")
        self.g.add(3, "Task", "In Review", parent=2, prs=[dict(OPEN_PR)])
        with mock.patch("builtins.print"):
            pipeline.review_done(self.cfg, WF, 3, override="reviewer đọc nhầm, đã có test ở x_test.py")
        self.assertEqual((self.st(3), self.g.issues[3]["rework_count"]), ("In Review", 0))
        self.assertTrue(any("omi:reviewed" in c and "bác BLOCKER" in c and "đọc nhầm" in c for c in self.g.notes[3]))
        self.assertTrue(any("bác BLOCKER" in c and "đọc nhầm" in c for c in self.g.notes[50]))  # comment PR
        with self.assertRaisesRegex(RuleError, "loại trừ"):
            pipeline.review_done(self.cfg, WF, 3, fail="x", override="y")

    def test_bug187_bug_without_parent_improve_goes_to_affects_and_qa_needs_review(self):
        self.g.add(2, "Functional Requirement", "Done", state="CLOSED")
        self.g.add(7, "Bug", "In Review", body="### Affects\n- #2", prs=[dict(OPEN_PR)])
        self.g.add(8, "Bug", "In Review", prs=[dict(OPEN_PR)])
        with mock.patch.object(pipeline, "run_cmd", side_effect=AssertionError("chưa review thì không chạy test")):
            with self.assertRaisesRegex(RuleError, "review-done 7"):
                pipeline.qa(self.cfg, WF, 7)
        self.assertEqual(self.st(7), "In Review")
        with mock.patch("builtins.print") as pr:
            pipeline.review_done(self.cfg, WF, 7, improve=["Tách hàm parse"])
            pipeline.review_done(self.cfg, WF, 8, improve=["Đặt tên rõ"])
        self.assertIn("- [ ] Tách hàm parse (từ #7)", next(c for c in self.g.notes[2] if "omi:findings" in c))
        self.assertIn("FINDINGS WARN #8", " ".join(str(c) for c in pr.call_args_list))
        self.assertTrue(any("omi:reviewed" in c for c in self.g.notes[8]))  # vẫn ghi REVIEWED
        with mock.patch.object(pipeline, "run_cmd", return_value=(0, "")), mock.patch("builtins.print"):
            self.assertEqual(pipeline.qa(self.cfg, WF, 7), 0)

    def test_review_done_fail_marks_and_reworks(self):
        self.g.add(2, "User Story", "In Progress")
        self.g.add(3, "Task", "In Review", parent=2, prs=[dict(OPEN_PR)])
        pipeline.review_done(self.cfg, WF, 3, "thiếu test cho case rỗng")
        self.assertEqual((self.st(3), self.g.issues[3]["rework_count"]), ("In Progress", 1))
        self.assertTrue(any("omi:reviewed" in c for c in self.g.notes[3]))

    def test_ac144_7_resume_prints_checkpoint_and_clears_when_done(self):
        from omi_hub.domain import handoff as hd
        self.g.add(2, "Functional Requirement", "In Progress")
        self.g.add(3, "Task", "In Progress", parent=2)
        self.T.mkdir(parents=True)
        (self.T / "current").write_text("3", encoding="utf-8")
        f = self.T.parent / "HANDOFF.md"
        f.write_text(hd.put_block("# HANDOFF\n", hd.WIP, "- Task: #3 · bước: code\n" + hd.INTENT + "sửa parser"),
                     encoding="utf-8")
        with mock.patch.object(pipeline, "run_cmd", side_effect=lambda cmd, cwd=None: (0, "3-x" if "rev-parse" in cmd else " M a.py")), mock.patch("builtins.print") as pr:
            self.assertEqual(pipeline.resume(self.cfg, WF), "code")
        out = "\n".join(str(c.args[0]) for c in pr.call_args_list if c.args)
        self.assertIn("## Checkpoint phiên trước\n- Task: #3 · bước: code\n- Ý định: sửa parser", out)
        self.g.issues[3].update(status="Done", state="CLOSED")
        with mock.patch.object(pipeline, "run_cmd", return_value=(0, "")), mock.patch("builtins.print"):
            self.assertEqual(pipeline.resume(self.cfg, WF), "next")
        self.assertIsNone(hd.get_block(f.read_text(encoding="utf-8"), hd.WIP))

    def test_bug195_resume_on_other_branch_asks_checkout(self):
        self.g.add(2, "Functional Requirement", "In Progress")
        self.g.add(455, "Task", "In Progress", parent=2)
        self.T.mkdir(parents=True)
        (self.T / "current").write_text("455", encoding="utf-8")
        run = lambda cmd, cwd=None: (0, "211-api" if "rev-parse" in cmd else "3")  # nhánh #211 có 3 commit
        with mock.patch.object(pipeline, "run_cmd", side_effect=run), mock.patch("builtins.print") as pr:
            self.assertEqual(pipeline.resume(self.cfg, WF), "branch")
        self.assertIn("RESUME #455 status=In Progress step=branch branch=211-api", pr.call_args_list[0].args[0])
        run = lambda cmd, cwd=None: (0, "455-x" if "rev-parse" in cmd else "0")
        with mock.patch.object(pipeline, "run_cmd", side_effect=run), mock.patch("builtins.print"):
            self.assertEqual(pipeline.resume(self.cfg, WF), "code")

    def test_resume_after_crash_before_review(self):
        self.g.add(2, "User Story", "In Progress")
        self.g.add(3, "Task", "In Review", parent=2, prs=[dict(OPEN_PR)])
        self.T.mkdir(parents=True)
        (self.T / "current").write_text("3", encoding="utf-8")
        (self.T / "review-3.md").write_text("pack", encoding="utf-8")
        with mock.patch.object(pipeline, "run_cmd", return_value=(0, "")):
            self.assertEqual(pipeline.resume(self.cfg, WF), "review")

    def test_ac142_1_done_or_cancelled_removes_task_files(self):
        self.g.add(2, "Functional Requirement", "In Progress")
        self.g.add(3, "Task", "In Review", parent=2, prs=[dict(OPEN_PR)])
        self.g.notes[3] = ["<!-- omi:reviewed -->"]
        self.g.add(4, "Task", "Ready", parent=2)
        self.T.mkdir(parents=True)
        for f in ("review-3.md", "qa-3.log", "review-4.md", "qa-4.log", "review-5.md"):
            (self.T / f).write_text("x", encoding="utf-8")
        with mock.patch.object(pipeline, "run_cmd", return_value=(0, "")), mock.patch("builtins.print") as pr:
            self.assertEqual(pipeline.qa(self.cfg, WF, 3), 0)
            items.move(self.cfg, WF, 4, "Cancelled", "không cần")
        self.assertIn(mock.call("DONE #3"), pr.call_args_list)
        self.assertEqual(sorted(f.name for f in self.T.iterdir()), ["review-5.md"])

    def test_ac144_4_qa_done_runs_handoff_errors_only_warn(self):
        self.g.add(2, "Functional Requirement", "In Progress", body=AC1)
        self.g.add(3, "Task", "In Review", parent=2, prs=[dict(OPEN_PR)])
        self.g.notes[3] = ["<!-- omi:reviewed -->"]
        pipeline.handoff.handoff.side_effect = OSError("disk")
        with mock.patch.object(pipeline, "run_cmd", return_value=(0, "test_ac2_1 ... ok")), mock.patch("builtins.print") as pr:
            self.assertEqual(pipeline.qa(self.cfg, WF, 3), 0)
        pipeline.handoff.handoff.assert_called_once_with(self.cfg, WF)
        self.assertEqual(pr.call_args, mock.call("HANDOFF WARN: disk"))
        self.assertEqual(self.st(3), "Done")

    def test_ac144_4_cli_move_cancelled_runs_handoff(self):
        from omi_hub.cli import main as cli
        for result, calls in (("Cancelled", 1), ("Ready", 0)):
            with mock.patch.object(cli, "load_cfg", return_value=self.cfg), \
                    mock.patch.object(cli.items, "move", return_value=result), \
                    mock.patch.object(cli.pipeline, "auto_handoff") as ah:
                cli.run(cli.build_parser().parse_args(["move", "3", result]), WF)
            self.assertEqual(ah.call_count, calls, result)

    def test_ac142_2_start_prunes_old_tmp_files(self):
        self.g.add(2, "Functional Requirement", "Approved")
        self.g.add(3, "Task", "Ready", parent=2)
        self.T.mkdir(parents=True)
        old = time.time() - 8 * 86400
        for f in ("review-1.md", "qa-1.log", "b51.md", "review-3.md", "current", "fresh.md"):
            (self.T / f).write_text("x", encoding="utf-8")
            if f != "fresh.md":
                os.utime(self.T / f, (old, old))
        with mock.patch("builtins.print") as pr:
            pipeline.start(self.cfg, WF, 3)
        self.assertIn(mock.call("Đã dọn 3 file cũ trong .omi/tmp"), pr.call_args_list)
        self.assertEqual(sorted(f.name for f in self.T.iterdir()), ["current", "fresh.md", "review-3.md"])
        with mock.patch("builtins.print") as pr:  # không có gì để dọn → không in
            pipeline.start(self.cfg, WF, 3)
        self.assertFalse(any("Đã dọn" in str(c) for c in pr.call_args_list))

    def test_ac142_3_resume_reviewed_task_without_pack_goes_to_qa(self):
        self.g.add(2, "Functional Requirement", "In Progress")
        self.g.add(3, "Task", "In Review", parent=2, prs=[dict(OPEN_PR)])
        self.g.notes[3] = ["<!-- omi:reviewed -->"]
        self.T.mkdir(parents=True)
        (self.T / "current").write_text("3", encoding="utf-8")  # gói review-3.md đã bị dọn
        with mock.patch.object(pipeline, "run_cmd", return_value=(0, "")), mock.patch("builtins.print"):
            self.assertEqual(pipeline.resume(self.cfg, WF), "qa")

    def test_resume_done_task_clears_current(self):
        self.g.add(3, "Task", "Done", state="CLOSED")
        self.T.mkdir(parents=True)
        (self.T / "current").write_text("3", encoding="utf-8")
        with mock.patch.object(pipeline, "run_cmd", return_value=(0, "")):
            self.assertEqual(pipeline.resume(self.cfg, WF), "next")
        self.assertFalse((self.T / "current").exists())


if __name__ == "__main__":
    unittest.main()
