import unittest

from support import WF
from omi_hub.domain import audit


def item(**kw):
    base = {"number": 1, "title": "t", "id": "N1", "type": "Task", "status": "Ready", "state": "OPEN",
            "state_reason": None, "milestone": "v1", "parent": 10, "blocked_reason": None,
            "open_blockers": 0, "in_project": True, "item_id": "I1", "priority": None, "milestone_due": None}
    base.update(kw)
    return base


STORY = item(number=10, type="User Story", status="In Progress", parent=20)
EPIC = item(number=20, type="Epic", status="In Progress", parent=None)


def inv(it, *others):
    by = {i["number"]: i for i in (it, STORY, EPIC, *others)}
    return audit.check_invariants(WF, it, by)


class TestInvariants(unittest.TestCase):
    def test_clean(self):
        self.assertEqual(inv(item()), [])

    def test_untyped(self):
        self.assertEqual(len(inv(item(type=None))), 1)

    def test_not_in_project(self):
        self.assertEqual(inv({"number": 5, "id": "N5", "type": "Bug", "in_project": False})[0]["fix"],
                         ("add", "Triage"))

    def test_closed_but_open_status(self):
        self.assertEqual(inv(item(state="CLOSED", state_reason="COMPLETED"))[0]["fix"], ("status", "Done"))
        self.assertEqual(inv(item(state="CLOSED", state_reason="NOT_PLANNED"))[0]["fix"], ("status", "Cancelled"))

    def test_open_but_terminal(self):
        self.assertEqual(inv(item(status="Done"))[0]["fix"], ("close", "Done"))

    def test_status_not_valid_for_type(self):
        self.assertIn("không hợp lệ", inv(item(status="Approved"))[0]["problem"])

    def test_wrong_parent(self):
        self.assertEqual(len(inv(item(parent=20))), 1)

    def test_done_with_open_child(self):
        done_story = item(number=10, type="User Story", status="Done", state="CLOSED", parent=20)
        child = item(number=1, status="Ready")
        probs = audit.check_invariants(WF, done_story, {1: child, 10: done_story, 20: EPIC})
        self.assertIn("con chưa kết thúc", probs[0]["problem"])

    def test_blocked_without_reason(self):
        self.assertEqual(len(inv(item(status="Blocked"))), 1)
        self.assertEqual(inv(item(status="Blocked", blocked_reason="x")), [])

    def test_waiting_without_open_blocker(self):
        self.assertEqual(inv(item(status="Waiting"))[0]["fix"], ("status", "Ready"))
        self.assertEqual(inv(item(status="Waiting", open_blockers=1)), [])
        self.assertEqual(inv(item(status="Ready", open_blockers=1))[0]["fix"], ("status", "Waiting"))

    def test_milestone_drift(self):
        self.assertEqual(inv(item(milestone="v2"))[0]["fix"], ("milestone", "v1"))

    def test_parent_outside_project_skipped(self):
        self.assertEqual(audit.check_invariants(WF, item(parent=99), {}), [])

if __name__ == "__main__":
    unittest.main()
