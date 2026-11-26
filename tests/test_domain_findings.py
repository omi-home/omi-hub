import unittest

from omi_hub.domain import findings


class TestFindings(unittest.TestCase):
    def test_add_dedupes_ignoring_source_case_spaces(self):
        its, ok = findings.add([], "Tách hàm  dài", 5)
        self.assertTrue(ok)
        self.assertEqual(its, [(False, "Tách hàm dài (từ #5)")])
        self.assertFalse(findings.add(its, "tách hàm dài", 6)[1])
        self.assertFalse(findings.add([(True, "Tách hàm dài (xong ở #7)")], "Tách hàm dài", 6)[1])

    def test_render_parse_roundtrip_and_stable_codes(self):
        its = [(True, "a (từ #1)"), (False, "b (từ #2)")]
        self.assertEqual(findings.parse(findings.render(its)), its)
        self.assertEqual(findings.open_codes(9, its), [("9.2", "b (từ #2)")])
