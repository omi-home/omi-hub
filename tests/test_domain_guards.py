import unittest

import support  # noqa: F401  (sys.path)
from omi_hub.domain import guards


def snap(**kw):
    base = {"number": 1, "type": "Task", "status": "Draft", "parent": None,
            "children": [], "open_blockers": 0, "prs": []}
    base.update(kw)
    return base


class TestGuards(unittest.TestCase):
    def ev(self, g, s, reason=None):
        return guards.evaluate_guards([g], s, reason)

    def test_reason(self):
        self.assertEqual(len(self.ev("reason", snap())), 1)
        self.assertEqual(len(self.ev("reason", snap(), "   ")), 1)
        self.assertEqual(self.ev("reason", snap(), "trùng #3"), [])

    def test_parent_ready(self):
        self.assertTrue(self.ev("parent_ready", snap()))
        self.assertTrue(self.ev("parent_ready", snap(parent={"number": 2, "type": "Functional Requirement", "status": "Draft"})))
        self.assertEqual(self.ev("parent_ready", snap(parent={"number": 2, "type": "Functional Requirement", "status": "Approved"})), [])
        self.assertEqual(self.ev("parent_ready", snap(parent={"number": 2, "type": "Functional Requirement", "status": "In Progress"})), [])

    def test_blockers(self):
        self.assertTrue(self.ev("no_open_blockers", snap(open_blockers=2)))
        self.assertEqual(self.ev("no_open_blockers", snap()), [])

    def test_prs(self):
        self.assertTrue(self.ev("pr_open", snap()))
        self.assertEqual(self.ev("pr_open", snap(prs=[{"number": 9, "state": "OPEN", "merged": False}])), [])
        self.assertTrue(self.ev("pr_merged", snap(prs=[{"number": 9, "state": "OPEN", "merged": False}])))
        self.assertEqual(self.ev("pr_merged", snap(prs=[{"number": 9, "state": "MERGED", "merged": True}])), [])

    def test_children_terminal(self):
        self.assertTrue(self.ev("children_terminal", snap(children=[{"status": "Done"}, {"status": "Ready"}])))
        self.assertEqual(self.ev("children_terminal", snap(children=[{"status": "Done"}, {"status": "Cancelled"}])), [])

    def test_impact(self):
        self.assertTrue(self.ev("impact_analysis", snap()))
        self.assertEqual(self.ev("impact_analysis", snap(has_impact=True)), [])

    def test_blocker_present(self):
        self.assertTrue(self.ev("blocker_present", snap()))
        self.assertEqual(self.ev("blocker_present", snap(), "chờ API key"), [])
        self.assertEqual(self.ev("blocker_present", snap(open_blockers=1)), [])

    def test_unknown_guard_is_error(self):
        with self.assertRaises(KeyError):
            guards.evaluate_guards(["nope"], snap())


if __name__ == "__main__":
    unittest.main()
