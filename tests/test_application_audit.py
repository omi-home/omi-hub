import unittest
from unittest import mock

from support import WF
from omi_hub.application import audit


def snap(item, **kw):
    """issue_snapshot giả theo dạng normalize_issue."""
    s = dict(item, parent=None, children=[], labels=[], prs=[], rework_count=0)
    s.pop("in_project", None)
    return dict(s, **kw)


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
        g.issue_snapshot.side_effect = lambda cfg, n: snap(items[n - 1])
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

    def test_fix_skipped_when_snapshot_stale(self):
        """Audit chụp lúc #3 chưa vào Project; apply thêm + set Ready ngay sau → không ghi đè về Draft."""
        g = mock.Mock()
        g.AUDIT_TITLE = "OMI Audit"
        g.project_items.return_value = []
        g.repo_issues.return_value = [{"number": 3, "title": "t", "state": "OPEN"}]
        task = {"item_id": None, "id": "N3", "number": 3, "title": "t", "type": "Task", "state": "OPEN",
                "state_reason": None, "status": None, "blocked_reason": None, "milestone": "v1",
                "open_blockers": 0}
        g.issue_snapshot.side_effect = [snap(task), snap(task, item_id="I3", status="Ready")]
        real, audit.gh = audit.gh, g
        try:
            audit.audit({}, WF, fix=True)
        finally:
            audit.gh = real
        g.add_to_project.assert_not_called()
        g.set_field.assert_not_called()


if __name__ == "__main__":
    unittest.main()
