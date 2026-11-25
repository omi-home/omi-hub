import unittest

from support import WF
from omi_hub.domain import planning


def item(**kw):
    base = {"number": 1, "title": "t", "id": "N1", "type": "Task", "status": "Ready", "state": "OPEN",
            "state_reason": None, "milestone": "v1", "parent": 10, "blocked_reason": None,
            "open_blockers": 0, "in_project": True, "item_id": "I1", "priority": None, "milestone_due": None}
    base.update(kw)
    return base


class TestPickNext(unittest.TestCase):
    def test_priority_then_milestone_then_number(self):
        items = [item(number=3, priority="P2"), item(number=4, priority="P1"),
                 item(number=2, priority="P1", milestone_due="2026-12-01"),
                 item(number=5, priority="P0", open_blockers=1),
                 item(number=6, priority="P0", status="In Progress"),
                 item(number=7, priority="P0", type="User Story", status="Approved")]
        self.assertEqual(planning.pick_next(WF, items)["number"], 2)

    def test_none(self):
        self.assertIsNone(planning.pick_next(WF, [item(status="Draft")]))


AC = "Mô tả\n\n### Acceptance criteria\n- [ ] ok"


class TestValidatePlan(unittest.TestCase):
    def plan(self, items, **kw):
        return {"milestone": "v1", "items": items, **kw}

    def test_valid(self):
        p = self.plan([{"key": "E001", "type": "Epic", "title": "E", "children": [
            {"key": "E001.S001", "type": "User Story", "title": "S", "body": AC, "children": [
                {"key": "E001.S001.T001", "type": "Task", "title": "T"}]}]}])
        self.assertEqual(planning.validate_plan(WF, p), [])

    def test_errors(self):
        p = self.plan([{"key": "E001", "type": "Epic", "title": "E", "children": [
            {"key": "E001", "type": "User Story", "title": "S"},
            {"key": "E001.T001", "type": "Task", "title": "T"},
            {"key": "E001.C001", "type": "Change Request", "title": "C"}]}], milestone=None)
        errs = planning.validate_plan(WF, p)
        self.assertTrue(any("trùng" in e for e in errs))
        self.assertTrue(any("Acceptance criteria" in e for e in errs))
        self.assertTrue(any("không được làm con" in e for e in errs))
        self.assertTrue(any("Change Request" in e for e in errs))
        self.assertTrue(any("milestone" in e for e in errs))

    def test_key_format_nnn(self):
        bad = self.plan([{"key": "E1", "type": "Epic", "title": "E"}])
        self.assertTrue(any("key 'E1'" in e for e in planning.validate_plan(WF, bad)))
        wrong_letter = self.plan([{"key": "E001", "type": "Epic", "title": "E", "children": [
            {"key": "E001.T001", "type": "User Story", "title": "S", "body": AC}]}])
        self.assertTrue(any("key 'E001.T001'" in e for e in planning.validate_plan(WF, wrong_letter)))

    def test_child_of_existing_issue(self):
        p = self.plan([{"key": "T001", "type": "Task", "title": "T", "parent": 42}])
        self.assertEqual(planning.validate_plan(WF, p), [])

    def test_milestone_only_on_root(self):
        p = self.plan([{"key": "E001", "type": "Epic", "title": "E", "milestone": "M0", "children": [
            {"key": "E001.S001", "type": "User Story", "title": "S", "body": AC, "milestone": "M1"}]},
            {"key": "T001", "type": "Task", "title": "T", "parent": 42, "milestone": "M1"}])
        errs = planning.validate_plan(WF, p)
        self.assertEqual([e.split(":")[0] for e in errs if "node gốc" in e], ["E001.S001", "T001"])

if __name__ == "__main__":
    unittest.main()
