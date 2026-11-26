import io
import unittest
from unittest import mock

import support  # noqa: F401  (sys.path tới scripts/)
from omi_hub.cli import main as cli
from omi_hub.domain.errors import RuleError
from omi_hub.infrastructure.github.client import GhError


class TestErrors(unittest.TestCase):
    def err(self, exc, argv=("status",)):
        out, er = io.StringIO(), io.StringIO()
        with mock.patch.object(cli.sys, "stdout", out), mock.patch.object(cli.sys, "stderr", er), \
                mock.patch.object(cli, "run", side_effect=exc):
            self.assertEqual(cli.main(list(argv)), 2)
        return er.getvalue()

    def test_ac139_4_internal_error_suggests_feedback(self):
        for exc in (GhError("gh api: HTTP 502"), KeyError("fields")):
            e = self.err(exc)
            self.assertIn('OMI_CLI feedback "status: ', e)
            self.assertIn("--kind bug --cmd status", e)
        self.assertIn("Traceback", self.err(KeyError("fields")))  # lỗi nội bộ kèm traceback để ghi feedback

    def test_ac139_4_user_error_no_feedback_hint(self):
        e = self.err(RuleError("#3 phải ở In Progress"))
        self.assertIn("❌ #3 phải ở In Progress", e)
        self.assertNotIn("feedback", e)


if __name__ == "__main__":
    unittest.main()
