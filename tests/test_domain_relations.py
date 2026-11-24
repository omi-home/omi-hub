import unittest

from support import WF
from omi_hub.domain import relations
from omi_hub.domain.errors import RuleError


class TestRelations(unittest.TestCase):
    def test_valid_parents(self):
        relations.check_parent(WF, "Task", "Functional Requirement")
        relations.check_parent(WF, "Non-Functional Requirement", "User Story")
        relations.check_parent(WF, "Epic", None)
        relations.check_parent(WF, "Bug", None)

    def test_wrong_parent(self):
        with self.assertRaisesRegex(RuleError, "không được làm con"):
            relations.check_parent(WF, "Task", "Epic")
        with self.assertRaisesRegex(RuleError, "không được làm con"):
            relations.check_parent(WF, "Epic", "Epic")

    def test_missing_required_parent(self):
        with self.assertRaisesRegex(RuleError, "bắt buộc có parent"):
            relations.check_parent(WF, "Task", None)

    def test_links(self):
        relations.check_links(WF, "Task", 0, False)
        with self.assertRaisesRegex(RuleError, "Affects"):
            relations.check_links(WF, "Change Request", 0, True)
        with self.assertRaisesRegex(RuleError, "milestone"):
            relations.check_links(WF, "Bug", 1, False)
        with self.assertRaisesRegex(RuleError, "milestone"):
            relations.check_links(WF, "Epic", 0, False)


class TestRollup(unittest.TestCase):
    def test_first_child_starts_parent(self):
        self.assertEqual(relations.rollup(WF, "User Story", "Approved", ["In Progress", "Ready"], "In Progress"),
                         "In Progress")

    def test_draft_parent_not_started(self):
        self.assertIsNone(relations.rollup(WF, "User Story", "Draft", ["In Progress"], "In Progress"))

    def test_all_children_done_story_to_qa(self):
        self.assertEqual(relations.rollup(WF, "Functional Requirement", "In Progress", ["Done", "Cancelled"], "Done"),
                         "In QA")

    def test_partial_children(self):
        self.assertIsNone(relations.rollup(WF, "User Story", "In Progress", ["Done", "In Review"], "Done"))

    def test_epic_and_cr_to_done(self):
        self.assertEqual(relations.rollup(WF, "Epic", "In Progress", ["Done", "Cancelled"], "Done"), "Done")
        self.assertEqual(relations.rollup(WF, "Change Request", "In Progress", ["Done"], "Done"), "Done")

    def test_all_cancelled_needs_human(self):
        self.assertIsNone(relations.rollup(WF, "Epic", "In Progress", ["Cancelled"], "Cancelled"))


if __name__ == "__main__":
    unittest.main()
