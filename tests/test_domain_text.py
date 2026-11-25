import unittest

import support  # noqa: F401  (sys.path)
from omi_hub.domain import text


class TestText(unittest.TestCase):
    def test_build_body(self):
        self.assertEqual(text.build_body("Mô tả", [12, 15], "E001.S001"),
                         "Mô tả\n\n### Affects\n#12 #15\n\n<!-- omi:key=E001.S001 -->")
        self.assertEqual(text.build_body("  "), "")

    def test_affected_roundtrip(self):
        self.assertEqual(text.affected(text.build_body("x", [3, 4])), [3, 4])
        self.assertEqual(text.affected("không có"), [])

    def test_find_marker_last_wins(self):
        texts = ["<!-- omi:blocked-from=Ready -->\n🚧", "khác", "<!-- omi:blocked-from=In Progress -->"]
        self.assertEqual(text.find_marker(texts, "blocked-from"), "In Progress")
        self.assertIs(text.find_marker(["a <!-- omi:impact --> b"], "impact"), True)
        self.assertIsNone(text.find_marker(["<!-- omi:rework n=1 stage=qa -->"], "impact"))

    def test_merge_agents_md(self):
        sec = f"{text.BEGIN}\nmới\n{text.END}"
        self.assertEqual(text.merge_agents_md("", sec), sec + "\n")
        self.assertEqual(text.merge_agents_md("# Dự án\n", sec), "# Dự án\n\n" + sec + "\n")
        old = f"# Dự án\n\n{text.BEGIN}\ncũ\n{text.END}\n\n## Khác\n"
        self.assertEqual(text.merge_agents_md(old, sec), f"# Dự án\n\n{sec}\n\n## Khác\n")




class TestDocRefs(unittest.TestCase):
    def test_section_stops_at_same_level_and_ignores_fenced_headings(self):
        from omi_hub.domain import docs
        md = "# A\n## Outbox pattern\nx\n```\n# không phải heading\n```\n### Con\ny\n## Khác\nz"
        self.assertEqual(docs.section(md, "outbox-pattern"),
                         "## Outbox pattern\nx\n```\n# không phải heading\n```\n### Con\ny")
        self.assertIsNone(docs.section(md, "nope"))
        self.assertEqual(docs.slug("Mục 3.4: Views (mẫu)"), "mục-34-views-mẫu")

    def test_doc_refs_only_in_section_deduped(self):
        from omi_hub.domain import docs
        body = "docs/truoc.md#x\n### Tham chiếu\n- docs/a.md#b\n- docs/a.md#b\n- docs/c.md\n### Khác\ndocs/x.md"
        self.assertEqual(docs.doc_refs(body), [("docs/a.md", "b"), ("docs/c.md", None)])


if __name__ == "__main__":
    unittest.main()
