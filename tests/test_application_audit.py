import unittest
from unittest import mock

from support import WF
from omi_hub.application import audit


class TestAudit(unittest.TestCase):
    def test_fixes_and_reports(self):
        items = [
            {"item_id": "I1", "id": "N1", "number": 1, "title": "e", "type": "Epic", "state": "OPEN",
             "state_reason": None, "status": "Done", "priority": None, "blocked_reason": None,
             "milestone": "v1", "milestone_due": None, "parent": None, "open_blockers": 0, "in_project": True},
            {"item_id": "I2", "id": "N2", "number": 2, "title": "t", "type": "Task", "state": "OPEN",
             "state_reason": None, "status": "Blocked", "priority": None, "blocked_reason": None,
             "milestone": "v1", "milestone_due": None, "parent": None, "open_blockers": 0, "in_project": True},
        ]
        g = mock.Mock()
        g.AUDIT_TITLE = "OMI Audit"
        g.project_items.return_value = items
        g.repo_issues.return_value = [{"number": 1, "title": "e", "state": "OPEN"},
                                      {"number": 2, "title": "t", "state": "OPEN"},
                                      {"number": 3, "title": "OMI Audit", "state": "OPEN"}]
        real, audit.gh = audit.gh, g
        try:
            code = audit.audit({}, WF, fix=True)
        finally:
            audit.gh = real
        g.close.assert_called_once_with({}, 1, "completed")
        body = g.upsert_audit_issue.call_args.args[1]
        self.assertIn("#2", body)            # Task thiếu parent + Blocked không lý do
        self.assertIn("[x] #1", body)        # Epic đã tự sửa
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
