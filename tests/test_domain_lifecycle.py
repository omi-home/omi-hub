import unittest

from support import WF
from omi_hub.domain import lifecycle
from omi_hub.domain.errors import RuleError


class TestWorkflowFile(unittest.TestCase):
    def test_every_status_used_is_declared(self):
        for t in WF["types"]:
            self.assertLessEqual(lifecycle.allowed_statuses(WF, t), set(WF["statuses"]), t)

    def test_status_sets_per_type(self):
        self.assertEqual(lifecycle.allowed_statuses(WF, "Epic"),
                         {"Draft", "Approved", "In Progress", "Blocked", "Done", "Cancelled"})
        self.assertEqual(lifecycle.allowed_statuses(WF, "User Story"),
                         {"Draft", "Approved", "In Progress", "In QA", "Blocked", "Done", "Cancelled"})
        self.assertEqual(lifecycle.allowed_statuses(WF, "Change Request"),
                         {"Triage", "Approved", "In Progress", "Blocked", "Done", "Cancelled"})
        self.assertEqual(lifecycle.allowed_statuses(WF, "Task"),
                         {"Draft", "Ready", "In Progress", "In Review", "In QA", "Blocked", "Done", "Cancelled"})
        self.assertEqual(lifecycle.allowed_statuses(WF, "Bug"),
                         {"Triage", "Ready", "In Progress", "In Review", "In QA", "Blocked", "Done", "Cancelled"})


class TestTransition(unittest.TestCase):
    def test_task_happy_path_guards(self):
        self.assertEqual(lifecycle.transition(WF, "Task", "Draft", "Ready"), ["parent_ready"])
        self.assertEqual(lifecycle.transition(WF, "Task", "Ready", "In Progress"), ["no_open_blockers"])
        self.assertEqual(lifecycle.transition(WF, "Task", "In Progress", "In Review"), ["pr_open"])
        self.assertEqual(lifecycle.transition(WF, "Task", "In Review", "In QA"), [])
        self.assertEqual(lifecycle.transition(WF, "Task", "In QA", "Done"), ["pr_merged"])

    def test_skip_step_rejected(self):
        with self.assertRaisesRegex(RuleError, "không được chuyển"):
            lifecycle.transition(WF, "Task", "Ready", "Done")

    def test_status_not_used_by_type(self):
        with self.assertRaisesRegex(RuleError, "không dùng"):
            lifecycle.transition(WF, "Task", "Draft", "Approved")

    def test_terminal_is_final(self):
        with self.assertRaisesRegex(RuleError, "kết thúc"):
            lifecycle.transition(WF, "User Story", "Done", "In Progress")

    def test_same_status_rejected(self):
        with self.assertRaisesRegex(RuleError, "đã ở"):
            lifecycle.transition(WF, "Task", "Ready", "Ready")

    def test_no_approved_back_to_draft(self):
        with self.assertRaises(RuleError):
            lifecycle.transition(WF, "Functional Requirement", "Approved", "Draft")

    def test_unknown_type(self):
        with self.assertRaisesRegex(RuleError, "không thuộc workflow"):
            lifecycle.transition(WF, "Feature", "Draft", "Ready")

    def test_cr_approve_needs_impact(self):
        self.assertEqual(lifecycle.transition(WF, "Change Request", "Triage", "Approved"), ["impact_analysis"])

    def test_needs_human(self):
        self.assertTrue(lifecycle.needs_human(WF, "Approved"))
        self.assertFalse(lifecycle.needs_human(WF, "Done"))

    def test_is_terminal(self):
        self.assertTrue(lifecycle.is_terminal(WF, "Cancelled"))
        self.assertFalse(lifecycle.is_terminal(WF, "Blocked"))


class TestBlocked(unittest.TestCase):
    def test_block_from_any_open_status(self):
        for st in ["Draft", "Ready", "In Progress", "In Review", "In QA"]:
            self.assertEqual(lifecycle.transition(WF, "Task", st, lifecycle.BLOCKED), ["blocker_present"])

    def test_cannot_block_terminal(self):
        with self.assertRaisesRegex(RuleError, "kết thúc"):
            lifecycle.transition(WF, "Task", "Done", "Blocked")

    def test_unblock_only_to_previous(self):
        self.assertEqual(lifecycle.transition(WF, "Task", "Blocked", "Ready", blocked_from="Ready"),
                         ["no_open_blockers"])
        with self.assertRaisesRegex(RuleError, "trước khi block"):
            lifecycle.transition(WF, "Task", "Blocked", "In Progress", blocked_from="Ready")


class TestRuleError(unittest.TestCase):
    def test_errors_list(self):
        self.assertEqual(RuleError("a").errors, ["a"])
        self.assertEqual(RuleError(["a", "b"]).errors, ["a", "b"])
        self.assertEqual(str(RuleError(["a", "b"])), "a; b")


if __name__ == "__main__":
    unittest.main()
