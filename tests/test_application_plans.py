import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from support import WF
from omi_hub.application import items, plans
from omi_hub.domain.errors import RuleError


class TestApply(unittest.TestCase):
    PLAN = {"milestone": "v1", "items": [
        {"key": "E001", "type": "Epic", "title": "Quản lý đơn hàng",
         "body": "### Mục tiêu\nBán hàng online\n\n### Phạm vi\n- đặt hàng", "children": [
            {"key": "E001.S001", "type": "User Story", "title": "Khách hàng có thể đặt hàng",
             "body": "### Story\nLà khách, tôi muốn đặt hàng để mua nhanh.\n\n### Acceptance criteria\n- [ ] a",
             "children": [{"key": "E001.S001.T001", "type": "Task", "title": "Thêm API đặt hàng",
                           "body": "### Việc cần làm\nPOST /orders\n\n### Definition of done\n- [ ] Test pass"}]}]}]}

    def run_apply(self, existing, approve):
        calls = []

        def fake_new(cfg, wf, type_, title, parent=None, **kw):
            calls.append((type_, parent, kw.get("status"), kw.get("key"), kw.get("milestone")))
            return 100 + len(calls)

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(self.PLAN, f)
        with mock.patch.object(items, "new_item", fake_new), \
                mock.patch.object(plans.gh, "existing_keys", return_value=existing), \
                mock.patch.object(plans.gh, "ensure_milestone") as em:
            keys = plans.apply({}, WF, f.name, approve)
        Path(f.name).unlink()
        em.assert_called_once_with({}, "v1")
        return calls, keys

    def test_creates_parent_first_with_approved_statuses(self):
        calls, keys = self.run_apply({}, approve=True)
        self.assertEqual(calls, [("Epic", None, "Approved", "E001", "v1"),
                                 ("User Story", 101, "Approved", "E001.S001", None),
                                 ("Task", 102, "Ready", "E001.S001.T001", None)])
        self.assertEqual(keys, {"E001": 101, "E001.S001": 102, "E001.S001.T001": 103})

    def test_idempotent_and_draft_without_approve(self):
        calls, keys = self.run_apply({"E001": {"number": 7, "title": "[Epic] Quản lý đơn hàng"}}, approve=False)
        self.assertEqual(calls, [("User Story", 7, None, "E001.S001", None), ("Task", 101, None, "E001.S001.T001", None)])
        self.assertEqual(keys["E001"], 7)

    def test_key_of_other_issue_rejected_before_creating(self):
        with self.assertRaisesRegex(RuleError, "key E001 đã là #1"):
            self.run_apply({"E001": {"number": 1, "title": "[Epic] Plan cũ"}}, approve=True)

    def test_invalid_plan_rejected(self):
        bad = {"items": [{"key": "T001", "type": "Task", "title": "x"}]}
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(bad, f)
        with self.assertRaisesRegex(RuleError, "bắt buộc có parent"):
            plans.apply({}, WF, f.name)
        Path(f.name).unlink()


if __name__ == "__main__":
    unittest.main()
