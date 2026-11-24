import unittest

import support  # noqa: F401  (sys.path)
from omi_hub.config import load_pr_template
from omi_hub.domain import acceptance, render, security
from omi_hub.domain.forms import render_pr_template
from omi_hub.domain.templates import check_pr

STORY_BODY = ("Là dev...\n\n### Acceptance criteria\n- [ ] đăng nhập được\n- [x] [manual] UI đúng mockup\n"
              "\n### Ghi chú\n- [ ] không tính")


class TestPipelineHelpers(unittest.TestCase):
    def test_parse_ac(self):
        acs = acceptance.parse_ac(STORY_BODY)
        self.assertEqual([(a["i"], a["manual"], a["checked"]) for a in acs], [(1, False, False), (2, True, True)])
        self.assertEqual(acceptance.parse_ac("không có mục"), [])

    def test_accept_verdict(self):
        acs = acceptance.parse_ac(STORY_BODY)
        self.assertEqual(acceptance.accept_verdict(12, acs, "test_ac12_1 ... ok", 0), (True, []))
        ok, missing = acceptance.accept_verdict(12, acs, "test_other ok", 0)
        self.assertFalse(ok)
        self.assertIn("ac12_1", missing[0])
        self.assertFalse(acceptance.accept_verdict(12, acs, "test_ac12_1 FAIL", 1)[0])
        unticked = acceptance.parse_ac("### Acceptance criteria\n- [ ] [manual] UI")
        self.assertEqual(acceptance.accept_verdict(5, unticked, "", 0), (False, ["AC1 [manual] chưa tick"]))

    def test_needs_security(self):
        self.assertTrue(security.needs_security(["README.md"], ["Security"]))
        self.assertTrue(security.needs_security(["src/auth/login.py"], []))
        self.assertFalse(security.needs_security(["README.md", "src/ui/button.tsx"], []))
        nfr = {"type": "Non-Functional Requirement", "body": "### Nhóm\n\nSecurity\n\n### Chỉ số và ngưỡng\n..."}
        self.assertTrue(security.needs_security(["README.md"], [], nfr))

    def test_tail(self):
        text = "\n".join(str(i) for i in range(100))
        self.assertEqual(render.tail(text).splitlines(), [str(i) for i in range(40, 100)])

    def test_render_context(self):
        s = {"number": 7, "type": "Task", "title": "[Task] Làm login", "status": "In Progress",
             "body": "Chi tiết\n\n<!-- omi:key=E001.S001.T001 -->"}
        parent = {"number": 10, "type": "User Story", "title": "[User Story] Khách có thể đăng nhập", "body": STORY_BODY}
        text = render.render_context(s, parent)
        self.assertIn("# #7 [Task] Làm login — In Progress", text)
        self.assertIn("đăng nhập được", text)
        self.assertIn("ac10_", text)
        self.assertNotIn("omi:key", text)
        self.assertNotIn("không tính", text)

    def test_render_plan(self):
        plan = {"items": [{"key": "E001", "type": "Epic", "title": "E", "children": [
            {"key": "E001.S001", "type": "User Story", "title": "S", "body": STORY_BODY}]}]}
        self.assertEqual(render.render_plan(plan), "E001 [Epic] E\n  E001.S001 [User Story] S (AC:2)")

    def test_pr_body_passes_pr_template(self):
        s = {"number": 7, "title": "[Task] Làm form đăng nhập", "body": ""}
        parent = {"number": 10, "type": "User Story", "title": "[User Story] Khách có thể đăng nhập", "body": STORY_BODY}
        body = render.render_pr_body(s, parent, ["#7: thêm form login"], True)
        pr_tpl = load_pr_template()
        self.assertEqual(check_pr(pr_tpl, render.pr_title(s), body), [])
        self.assertIn("ac10_1", body)
        self.assertNotIn("ac10_2", body)  # AC [manual] không có test
        self.assertIn("Có chạm security", body)

    def test_pr_template_md_must_be_filled(self):
        pr_tpl = load_pr_template()
        errs = check_pr(pr_tpl, "[Task] Làm form đăng nhập (#7)", render_pr_template(pr_tpl))
        self.assertTrue(any("Liên kết" in e for e in errs))
        self.assertTrue(any("Security" in e for e in errs))


if __name__ == "__main__":
    unittest.main()
