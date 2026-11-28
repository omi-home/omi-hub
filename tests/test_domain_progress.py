import unittest

from support import WF
from omi_hub.domain.progress import render_status, resume_step


def pitem(n, type_, status, parent=None, **kw):
    base = {"number": n, "title": f"[{type_}] item {n}", "type": type_, "status": status, "state": "OPEN",
            "parent": parent, "milestone": "v1", "milestone_due": None, "priority": "P1",
            "open_blockers": 0, "blocked_reason": None, "rework_count": 0}
    base.update(kw)
    return base


class TestStatusResume(unittest.TestCase):
    def test_render_status(self):
        items = [pitem(1, "Epic", "In Progress"), pitem(2, "User Story", "In Progress", 1),
                 pitem(3, "Task", "Done", 2), pitem(4, "Task", "In Review", 2, rework_count=2),
                 pitem(5, "Task", "Blocked", 2, blocked_reason="chờ API key"), pitem(6, "Task", "Ready", 2),
                 pitem(7, "Task", "Cancelled", 2)]
        out = render_status(WF, items)
        self.assertIn("STATUS: 1/6 (16%) item Done · Task/Bug 1/4 (25%)", out)
        self.assertIn("- #1 [Epic] item 1 — In Progress · 1/5 (20%)", out)
        self.assertIn("- #4 [Task] item 4 — In Review", out)
        self.assertIn("chờ API key", out)
        self.assertIn("2 lần", out)
        self.assertIn("Tiếp theo: #6", out)
        self.assertIn("STATUS v2: 0/0", render_status(WF, items, "v2"))

    def test_ac105_2_status_lists_waiting(self):
        items = [pitem(1, "Task", "Waiting", blockers=[3, 4], open_blockers=2), pitem(2, "Task", "Ready")]
        out = render_status(WF, items)
        self.assertIn("Waiting:\n- #1 [Task] item 1 — chờ #3, #4", out)
        self.assertNotIn("#2 [Task] item 2 — chờ", out)

    def test_resume_step(self):
        rs = resume_step
        self.assertEqual(rs("In Progress", True, 0, False, False)[0], "code")
        self.assertEqual(rs("In Progress", False, 0, False, False)[0], "code")
        self.assertEqual(rs("In Progress", False, 2, False, False)[0], "submit")
        self.assertEqual(rs("In Progress", False, 0, False, False, on_branch=False)[0], "branch")  # bug #195
        self.assertEqual(rs("In Review", False, 2, False, True)[0], "review")
        self.assertIn("submit", rs("In Review", False, 2, False, False)[1])  # mất gói review → submit lại
        self.assertEqual(rs("In Review", False, 2, True, True)[0], "qa")
        self.assertEqual(rs("In QA", False, 0, True, False)[0], "qa")
        self.assertEqual(rs("Blocked", False, 0, False, False)[0], "blocked")
        self.assertEqual(rs("Ready", False, 0, False, False)[0], "start")
        self.assertEqual(rs("Done", False, 0, True, False)[0], "next")


if __name__ == "__main__":
    unittest.main()
