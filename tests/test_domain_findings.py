import unittest

from omi_hub.domain import findings


class TestFindings(unittest.TestCase):
    def test_add_dedupes_ignoring_source_case_spaces(self):
        its, ok = findings.add([], "Tách hàm  dài", "từ #5")
        self.assertTrue(ok)
        self.assertEqual(its, [(False, "Tách hàm dài (từ #5)")])
        self.assertFalse(findings.add(its, "tách hàm dài", "từ #6")[1])
        self.assertFalse(findings.add([(True, "Tách hàm dài (xong ở #7)")], "Tách hàm dài", "chuyển từ #6")[1])

    def test_render_parse_roundtrip_and_stable_codes(self):
        its = [(True, "a (từ #1)"), (False, "b (từ #2)")]
        self.assertEqual(findings.parse(findings.render(its)), its)
        self.assertEqual(findings.open_codes(9, its), [("9.2", "b (từ #2)")])

    def test_mark_and_parse_codes(self):
        its = [(False, "a"), (False, "b")]
        self.assertEqual(findings.mark(its, {2}, "xong ở #4"), [(False, "a"), (True, "b (xong ở #4)")])
        self.assertEqual(findings.parse_codes("12.1, 12.3,7.2"), {12: {1, 3}, 7: {2}})
        with self.assertRaisesRegex(Exception, "sai dạng"):
            findings.parse_codes("12")
