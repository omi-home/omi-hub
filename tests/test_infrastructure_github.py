import json
import unittest
from unittest import mock

import support  # noqa: F401  (sys.path)
from omi_hub.infrastructure.github import client, issues, project, pulls

PID = "PROJ"


def pitem(pid=PID, status=None, rework=None, blocked=None, iid="ITEM"):
    return {"id": iid, "project": {"id": pid},
            "status": {"name": status} if status else None,
            "rework": {"number": rework} if rework is not None else None,
            "blocked": {"text": blocked} if blocked else None}


RAW = {
    "id": "I_1", "number": 7, "title": "Làm X", "body": "b", "state": "OPEN", "stateReason": None,
    "issueType": {"name": "Task"}, "milestone": {"title": "v1"}, "labels": {"nodes": [{"name": "security"}]},
    "parent": {"number": 3, "issueType": {"name": "Functional Requirement"}, "projectItems": {"nodes": [pitem(status="Approved")]}},
    "subIssues": {"nodes": []},
    "blockedBy": {"nodes": [{"number": 1, "state": "OPEN"}, {"number": 2, "state": "CLOSED"}]},
    "closedByPullRequestsReferences": {"nodes": [{"number": 9, "state": "OPEN", "merged": False}]},
    "projectItems": {"nodes": [pitem(pid="OTHER", status="Done", iid="X"),
                               pitem(status="In Review", rework=2.0, iid="ITEM")]},
}


class TestNormalize(unittest.TestCase):
    def test_issue(self):
        s = issues.normalize_issue(RAW, PID)
        self.assertEqual(s["type"], "Task")
        self.assertEqual(s["item_id"], "ITEM")
        self.assertEqual(s["status"], "In Review")
        self.assertEqual(s["rework_count"], 2)
        self.assertEqual(s["parent"], {"number": 3, "type": "Functional Requirement", "status": "Approved"})
        self.assertEqual(s["open_blockers"], 1)
        self.assertEqual(s["prs"], [{"number": 9, "state": "OPEN", "merged": False}])
        self.assertEqual(s["milestone"], "v1")
        self.assertEqual(s["labels"], ["security"])

    def test_issue_not_in_project(self):
        raw = dict(RAW, projectItems={"nodes": []}, parent=None, issueType=None, milestone=None)
        s = issues.normalize_issue(raw, PID)
        self.assertIsNone(s["item_id"])
        self.assertIsNone(s["status"])
        self.assertIsNone(s["type"])
        self.assertEqual(s["rework_count"], 0)

    def test_project_item(self):
        node = {"id": "ITEM", "status": {"name": "Ready"}, "priority": {"name": "P1"}, "blocked": None,
                "content": {"id": "I_7", "number": 7, "title": "t", "state": "OPEN", "stateReason": None,
                            "issueType": {"name": "Task"}, "milestone": {"title": "v1", "dueOn": "2026-12-01T00:00:00Z"},
                            "parent": {"number": 3}, "blockedBy": {"nodes": [{"state": "OPEN"}]}}}
        it = project.normalize_project_item(node)
        self.assertEqual((it["number"], it["status"], it["priority"], it["parent"], it["open_blockers"]),
                         (7, "Ready", "P1", 3, 1))
        self.assertEqual(it["milestone_due"], "2026-12-01T00:00:00Z")
        self.assertTrue(it["in_project"])

    def test_project_item_skips_non_issue(self):
        self.assertIsNone(project.normalize_project_item({"id": "X", "content": {}}))


CFG = {"owner": "o", "repo": "r", "project_id": PID, "fields": {
    "Status": {"id": "F_S", "options": {"Ready": "OPT_R"}},
    "Rework Count": {"id": "F_R"}, "Blocked Reason": {"id": "F_B"}}}


class TestSetField(unittest.TestCase):
    def test_single_select(self):
        with mock.patch.object(client, "graphql") as g:
            project.set_field(CFG, "ITEM", "Status", "Ready")
        self.assertEqual(g.call_args.kwargs["value"], {"singleSelectOptionId": "OPT_R"})

    def test_number_and_text(self):
        with mock.patch.object(client, "graphql") as g:
            project.set_field(CFG, "ITEM", "Rework Count", 2)
            self.assertEqual(g.call_args.kwargs["value"], {"number": 2.0})
            project.set_field(CFG, "ITEM", "Blocked Reason", "chờ")
            self.assertEqual(g.call_args.kwargs["value"], {"text": "chờ"})

    def test_add_to_project_when_github_auto_added(self):
        with mock.patch.object(client, "graphql", side_effect=[
                client.GhError("Content already exists in this project"),
                {"node": {"projectItems": {"nodes": [{"id": "ITEM9", "project": {"id": PID}}]}}}]):
            self.assertEqual(project.add_to_project(CFG, "I_9"), "ITEM9")

    def test_unknown_option(self):
        with self.assertRaisesRegex(client.GhError, "không có option"):
            project.set_field(CFG, "ITEM", "Status", "Nope")


class TestRun(unittest.TestCase):
    def test_error_hint(self):
        fake = mock.Mock(returncode=1, stdout="", stderr="INSUFFICIENT_SCOPES: need project")
        with mock.patch("subprocess.run", return_value=fake):
            with self.assertRaisesRegex(client.GhError, "gh auth refresh"):
                client.run(["api", "graphql"])

    def test_graphql_sends_json(self):
        fake = mock.Mock(returncode=0, stdout=json.dumps({"data": {"ok": 1}}), stderr="")
        with mock.patch("subprocess.run", return_value=fake) as r:
            self.assertEqual(client.graphql("query{x}", a=1), {"ok": 1})
        self.assertEqual(json.loads(r.call_args.kwargs["input"]), {"query": "query{x}", "variables": {"a": 1}})


class TestIssueOps(unittest.TestCase):
    CFG = {"owner": "o", "repo": "r"}

    def test_existing_keys(self):
        out = json.dumps([{"number": 3, "body": "x\n<!-- omi:key=E001.S001 -->"}, {"number": 4, "body": None}])
        with mock.patch.object(client, "run", return_value=out):
            self.assertEqual(issues.existing_keys(self.CFG), {"E001.S001": 3})

    def test_upsert_audit_issue(self):
        open_audit = [{"number": 8, "title": issues.AUDIT_TITLE, "state": "OPEN"}]
        with mock.patch.object(issues, "repo_issues", return_value=open_audit), \
                mock.patch.object(client, "rest") as r:
            issues.upsert_audit_issue(self.CFG, "body")
            self.assertEqual(r.call_args.args[:2], ("PATCH", "repos/o/r/issues/8"))
            issues.upsert_audit_issue(self.CFG, None)
            self.assertEqual(r.call_args.args[2], {"state": "closed", "state_reason": "completed"})
        with mock.patch.object(issues, "repo_issues", return_value=[]), mock.patch.object(client, "rest") as r:
            issues.upsert_audit_issue(self.CFG, "body")
            self.assertEqual(r.call_args.args[:2], ("POST", "repos/o/r/issues"))

    def test_pr_checks_fail_appends_failed_run_log(self):
        table = ("gh pr checks 4: pr-lint\tfail\t4s\thttps://github.com/o/r/actions/runs/77/job/1\t\n"
                 "audit\tskipping\t0\thttps://github.com/o/r/actions/runs/88/job/2\t\n"
                 "pr-lint\tfail\t4s\thttps://github.com/o/r/actions/runs/77/job/1\t")
        calls = []

        def fake(args, **kw):
            calls.append(args)
            if args[:2] == ["pr", "checks"]:
                raise client.GhError(table)
            return "pr-lint\tcheckout\t##[error]Input required and not supplied: token"

        with mock.patch.object(client, "run", side_effect=fake):
            ok, out = pulls.pr_checks(self.CFG, 4)
        self.assertFalse(ok)
        self.assertIn("Input required and not supplied: token", out)
        self.assertEqual([c[2] for c in calls if c[0] == "run"], ["77"])  # chỉ run fail, không trùng

    def test_close_tolerates_already_closed(self):
        err = client.GhError("gh api -X PATCH: gh: Validation Failed (HTTP 422)")
        with mock.patch.object(client, "rest", side_effect=[err, {"state": "closed"}]):
            issues.close(self.CFG, 2, "completed")  # Project đã tự đóng → không lỗi
        with mock.patch.object(client, "rest", side_effect=[err, {"state": "open"}]):
            with self.assertRaises(client.GhError):
                issues.close(self.CFG, 2, "completed")


if __name__ == "__main__":
    unittest.main()
