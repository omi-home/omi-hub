import contextlib
import io
import unittest
from unittest import mock

from support import WF
from omi_hub.application import items, views
from omi_hub.cli.main import main
from omi_hub.domain.errors import RuleError
CFG = {}
FIELD_KEY = {"Status": "status", "Rework Count": "rework_count", "Blocked Reason": "blocked_reason"}


class FakeGh:
    """GitHub trong bộ nhớ, đủ cho các lệnh move/rework/block."""

    def __init__(self):
        self.issues, self.notes, self.assigned, self.blockers = {}, {}, [], {}

    def add(self, n, type_, status, parent=None, state="OPEN", prs=(), body="", labels=()):
        self.issues[n] = {"number": n, "id": f"N{n}", "title": f"#{n}", "type": type_, "status": status,
                          "parent": parent, "state": state, "state_reason": None, "prs": list(prs),
                          "body": body, "rework_count": 0, "blocked_reason": None,
                          "open_blockers": 0, "milestone": "v1", "labels": list(labels)}

    def issue_snapshot(self, cfg, n):
        s = dict(self.issues[n], item_id=f"I{n}")
        s["open_blockers"] += sum(self.issues[b]["state"] == "OPEN" for b in self.blockers.get(n, []))
        p = self.issues.get(s["parent"])
        s["parent"] = {"number": p["number"], "type": p["type"], "status": p["status"]} if p else None
        s["children"] = [{"number": c["number"], "type": c["type"], "status": c["status"], "state": c["state"]}
                         for c in self.issues.values() if c["parent"] == n]
        return s

    def set_field(self, cfg, item_id, field, value):
        self.issues[int(item_id[1:])][FIELD_KEY[field]] = value

    def clear_field(self, cfg, item_id, field):
        self.set_field(cfg, item_id, field, None)

    def comment(self, cfg, n, body):
        self.notes.setdefault(n, []).append(body)

    def comments(self, cfg, n):
        return self.notes.get(n, [])

    def close(self, cfg, n, reason):
        self.issues[n]["state"] = "CLOSED"

    def assign_self(self, cfg, n):
        self.assigned.append(n)

    def milestone_open_issues(self, cfg, title):
        return sum(1 for i in self.issues.values() if i["milestone"] == title and i["state"] == "OPEN")

    def open_dependents(self, cfg, n):
        return [d for d, bs in self.blockers.items() if n in bs and self.issues[d]["state"] == "OPEN"]


MERGED = [{"number": 99, "state": "MERGED", "merged": True}]


class TestFlow(unittest.TestCase):
    def setUp(self):
        self.real, self.g = items.gh, FakeGh()
        items.gh = self.g

    def tearDown(self):
        items.gh = self.real

    def st(self, n):
        return self.g.issues[n]["status"]

    def test_first_task_start_rolls_up_chain(self):
        self.g.add(1, "Epic", "Approved")
        self.g.add(2, "User Story", "Approved", parent=1)
        self.g.add(3, "Task", "Ready", parent=2)
        items.move(CFG, WF, 3, "In Progress")
        self.assertEqual((self.st(3), self.st(2), self.st(1)), ("In Progress", "In Progress", "In Progress"))
        self.assertEqual(self.g.assigned, [3])

    def test_last_task_done_moves_story_to_qa(self):
        self.g.add(1, "Epic", "In Progress")
        self.g.add(2, "User Story", "In Progress", parent=1)
        self.g.add(3, "Task", "In QA", parent=2, prs=MERGED)
        self.g.add(4, "Task", "Done", parent=2, state="CLOSED")
        items.move(CFG, WF, 3, "Done")
        self.assertEqual((self.st(3), self.g.issues[3]["state"]), ("Done", "CLOSED"))
        self.assertEqual(self.st(2), "In QA")
        self.assertEqual(self.st(1), "In Progress")

    def test_move_idempotent_still_rolls_up(self):
        self.g.add(2, "User Story", "In Progress")
        self.g.add(3, "Task", "Done", parent=2, state="CLOSED")  # PR merge + built-in workflow đã set Done
        items.move(CFG, WF, 3, "Done")
        self.assertEqual(self.st(2), "In QA")

    def test_story_done_closes_epic(self):
        self.g.add(1, "Epic", "In Progress")
        self.g.add(2, "User Story", "In QA", parent=1)
        items.move(CFG, WF, 2, "Done")
        self.assertEqual(self.st(1), "Done")

    def test_guard_blocks_done_without_merged_pr(self):
        self.g.add(2, "User Story", "In Progress")
        self.g.add(3, "Task", "In QA", parent=2)
        with self.assertRaisesRegex(RuleError, "chưa merge"):
            items.move(CFG, WF, 3, "Done")
        self.assertEqual(self.st(3), "In QA")

    def test_story_done_blocked_by_child_added_during_qa(self):
        self.g.add(2, "User Story", "In QA")
        self.g.add(3, "Task", "Draft", parent=2)  # con thêm sau khi story vào QA
        with self.assertRaisesRegex(RuleError, "con chưa Done"):
            items.move(CFG, WF, 2, "Done")
        self.assertEqual(self.st(2), "In QA")

    def test_rework_counts_and_comments(self):
        self.g.add(2, "User Story", "In Progress")
        self.g.add(3, "Task", "In Review", parent=2)
        self.assertEqual(items.rework(CFG, WF, 3, "thiếu test"), "In Progress")
        self.assertEqual((self.st(3), self.g.issues[3]["rework_count"]), ("In Progress", 1))
        self.assertIn("omi:rework n=1 stage=review", self.g.notes[3][0])

    def test_rework_limit_blocks_then_unblock_returns_in_progress(self):
        self.g.add(2, "User Story", "In Progress")
        self.g.add(3, "Task", "In QA", parent=2)
        self.g.issues[3]["rework_count"] = 3
        self.assertEqual(items.rework(CFG, WF, 3, "vẫn fail"), "Blocked")
        self.assertEqual(self.st(3), "Blocked")
        self.assertTrue(self.g.issues[3]["blocked_reason"])
        items.unblock(CFG, WF, 3)
        self.assertEqual((self.st(3), self.g.issues[3]["blocked_reason"]), ("In Progress", None))

    def test_block_requires_reason(self):
        self.g.add(3, "Task", "Ready", parent=None)
        with self.assertRaisesRegex(RuleError, "--reason"):
            items.block(CFG, WF, 3)

    def test_new_user_story_rejected(self):
        with self.assertRaisesRegex(RuleError, "không còn tạo mới"):
            items.new_item(CFG, WF, "User Story", "Khách có thể đặt hàng", parent=1)

    def test_cancel_requires_reason(self):
        self.g.add(3, "Task", "Ready")
        with self.assertRaisesRegex(RuleError, "--reason"):
            items.move(CFG, WF, 3, "Cancelled")

    def test_cr_done_writes_changelog_on_affected(self):
        self.g.add(1, "Epic", "In Progress")
        self.g.add(2, "User Story", "Done", parent=1, state="CLOSED")
        self.g.add(5, "Change Request", "In Progress", parent=1, body="x\n\n### Affects\n#2")
        self.g.add(6, "Task", "In QA", parent=5, prs=MERGED)
        items.move(CFG, WF, 6, "Done")
        self.assertEqual(self.st(5), "Done")
        self.assertIn("Change Request #5", self.g.notes[2][-1])
        self.assertEqual(self.st(1), "Done")

    def test_ready_with_open_blocker_goes_waiting_then_auto_ready(self):
        self.g.add(2, "User Story", "Approved")
        self.g.add(3, "Task", "In QA", parent=2, prs=MERGED)
        self.g.add(4, "Task", "Draft", parent=2)
        self.g.add(5, "Task", "Draft", parent=2)
        self.g.blockers = {4: [3], 5: [3, 6]}
        self.g.add(6, "Task", "Ready", parent=2)
        items.move(CFG, WF, 4, "Ready")
        items.move(CFG, WF, 5, "Ready")
        self.assertEqual((self.st(4), self.st(5)), ("Waiting", "Waiting"))
        items.move(CFG, WF, 3, "Done")
        self.assertEqual((self.st(4), self.st(5)), ("Ready", "Waiting"))  # #5 còn chờ #6
        self.assertIn("hết blocker (#3", self.g.notes[4][-1])
        with self.assertRaisesRegex(RuleError, "blocked-by đang mở"):
            items.move(CFG, WF, 5, "Ready")

    def test_milestone_ready_printed_once_when_last_issue_closes(self):
        self.g.add(1, "Epic", "In Progress")
        self.g.add(2, "Change Request", "In Progress", parent=1)
        self.g.add(3, "Task", "In QA", parent=2, prs=MERGED)
        self.g.add(4, "Task", "In QA", parent=2, prs=MERGED)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            items.move(CFG, WF, 3, "Done")
        self.assertNotIn("MILESTONE", out.getvalue())
        with contextlib.redirect_stdout(out):
            items.move(CFG, WF, 4, "Done")  # rollup đóng CR rồi Epic → milestone hết issue mở
        self.assertEqual(out.getvalue().count("MILESTONE v1 sẵn sàng release"), 1)


class TestViews(unittest.TestCase):
    ITEMS = [{"number": 1, "title": "[Epic] E", "status": "In Progress", "parent": None, "type": "Epic",
              "state": "OPEN", "open_blockers": 0, "priority": None, "milestone_due": None},
             {"number": 2, "title": "[Task] T", "status": "Ready", "parent": 1, "type": "Task",
              "state": "OPEN", "open_blockers": 0, "priority": "P1", "milestone_due": None},
             {"number": 9, "title": "OMI Audit", "status": None, "parent": None, "type": None,
              "state": "OPEN", "open_blockers": 0, "priority": None, "milestone_due": None}]

    def setUp(self):
        self.real = views.gh
        views.gh = mock.Mock(project_items=mock.Mock(return_value=self.ITEMS), AUDIT_TITLE="OMI Audit")

    def tearDown(self):
        views.gh = self.real

    def test_tree(self):
        self.assertEqual(views.tree(CFG), ["#1 [Epic] E — In Progress", "  #2 [Task] T — Ready"])
        with self.assertRaises(RuleError):
            views.tree(CFG, 5)

    def test_ac105_1_tree_shows_open_blockers(self):
        items = [dict(self.ITEMS[0]), dict(self.ITEMS[1], status="Waiting", blockers=[7, 8], open_blockers=2)]
        views.gh.project_items.return_value = items
        self.assertEqual(views.tree(CFG), ["#1 [Epic] E — In Progress", "  #2 [Task] T — Waiting ⛔ #7, #8"])

    def test_next(self):
        self.assertEqual(views.next_item(CFG, WF)["number"], 2)


class TestCli(unittest.TestCase):
    def test_template(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(main(["template", "Task"]), 0)
        self.assertIn("### Việc cần làm", out.getvalue())


if __name__ == "__main__":
    unittest.main()
