import unittest

from support import WF
from omi_hub.domain import rework
from omi_hub.domain.errors import RuleError


class TestRework(unittest.TestCase):
    def test_from_review(self):
        self.assertEqual(rework.rework(WF, "Task", "In Review", 0), ("In Progress", 1))

    def test_story_from_qa(self):
        self.assertEqual(rework.rework(WF, "User Story", "In QA", 1), ("In Progress", 2))

    def test_limit_blocks(self):
        self.assertEqual(rework.rework(WF, "Task", "In QA", 3), ("Blocked", 4))

    def test_invalid_source(self):
        with self.assertRaisesRegex(RuleError, "Rework"):
            rework.rework(WF, "Task", "In Progress", 0)

    def test_type_without_qa(self):
        with self.assertRaises(RuleError):
            rework.rework(WF, "Epic", "In QA", 0)


if __name__ == "__main__":
    unittest.main()
