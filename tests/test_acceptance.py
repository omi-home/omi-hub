"""Test nghiệm thu: mỗi AC tự động của story có test `ac<n>_<i>` chạy bộ test tương ứng (omi accept dùng -k ac{n}_)."""
import io
import unittest
from pathlib import Path

import support  # noqa: F401  (sys.path)

HERE = Path(__file__).resolve().parent


class TestAcceptance(unittest.TestCase):
    def suite_passes(self, pattern):
        # loader mới: `-k ac{n}_` gắn bộ lọc tên vào defaultTestLoader, sẽ lọc mất bộ test bên trong
        suite = unittest.TestLoader().discover(str(HERE), pattern=pattern, top_level_dir=str(HERE))
        r = unittest.TextTestRunner(stream=io.StringIO()).run(suite)
        self.assertGreater(r.testsRun, 0, pattern)
        self.assertTrue(r.wasSuccessful(), f"{pattern}: {len(r.failures)} fail, {len(r.errors)} error")

    def test_ac4_1_domain_rules_suite(self):  # #4 AC1: luật thuần (transition … template)
        self.suite_passes("test_domain_*.py")

    def test_ac10_1_github_layer_suite(self):  # #10 AC1: lớp gh
        self.suite_passes("test_infrastructure_github.py")

    def test_ac13_1_cli_suite(self):  # #13 AC1: CLI / use case
        self.suite_passes("test_application_*.py")

    def test_ac21_1_hook_suite(self):  # #21 AC1: hook gác cổng
        self.suite_passes("test_guard.py")


if __name__ == "__main__":
    unittest.main()
