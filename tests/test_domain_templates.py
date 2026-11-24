import unittest

from support import WF
from omi_hub.config import load_pr_template, load_templates
from omi_hub.domain import planning, templates
from omi_hub.domain.errors import RuleError

TPL = load_templates()
PR_TPL = load_pr_template()
STORY_OK = "### Story\nLà khách, tôi muốn đặt hàng để mua nhanh.\n\n### Acceptance criteria\n- [ ] đặt được hàng"


class TestTemplates(unittest.TestCase):
    def test_every_workflow_type_has_template(self):
        self.assertEqual(set(TPL), set(WF["types"]))

    def test_prefix_full_names(self):
        self.assertEqual({templates.prefix(t) for t in TPL},
                         {"[Epic] ", "[User Story] ", "[Functional Requirement] ", "[Non-Functional Requirement] ",
                          "[Change Request] ", "[Task] ", "[Bug] "})

    def test_with_prefix_idempotent(self):
        self.assertEqual(templates.with_prefix(TPL, "Functional Requirement", "Hệ thống phải X"), "[Functional Requirement] Hệ thống phải X")
        self.assertEqual(templates.with_prefix(TPL, "Functional Requirement", "[Functional Requirement] Hệ thống phải X"),
                         "[Functional Requirement] Hệ thống phải X")

    def test_sections_parse(self):
        self.assertEqual(templates.sections("intro\n### A\nx\n\n### B\n_No response_\n### C\n<!-- gợi ý -->\n"),
                         {"A": "x", "B": "", "C": ""})

    def test_valid_story(self):
        self.assertEqual(templates.check_template(TPL, "User Story", "[User Story] Khách hàng có thể đặt hàng", STORY_OK), [])

    def test_missing_or_abbreviated_prefix(self):
        errs = templates.check_template(TPL, "User Story", "Khách hàng có thể đặt hàng", STORY_OK)
        self.assertEqual(len(errs), 1)
        self.assertIn("[User Story]", errs[0])
        errs = templates.check_template(TPL, "Functional Requirement", "[FR] Hệ thống phải gửi mail", "### Mô tả\nx\n\n### Acceptance criteria\n- [ ] y")
        self.assertTrue(any("[Functional Requirement]" in e for e in errs))

    def test_bad_title_pattern(self):
        errs = templates.check_template(TPL, "Functional Requirement", "[Functional Requirement] Gửi email",
                                    "### Mô tả\nx\n\n### Acceptance criteria\n- [ ] y")
        self.assertEqual(len(errs), 1)
        self.assertIn("Hệ thống phải", errs[0])

    def test_missing_and_default_sections(self):
        errs = templates.check_template(TPL, "User Story", "[User Story] Khách có thể mua",
                                    "### Story\nLà <vai trò>, tôi muốn <hành động> để <giá trị>.")
        self.assertTrue(any("Story" in e for e in errs))
        self.assertTrue(any("Acceptance criteria" in e for e in errs))

    def test_checklist_options_pattern(self):
        self.assertTrue(templates.check_template(TPL, "Task", "[Task] Thêm API đặt hàng",
                                             "### Việc cần làm\nx\n\n### Definition of done\nchỉ chữ"))
        nfr = ("### Nhóm\nNhanh\n\n### Chỉ số và ngưỡng\np95<300ms\n\n### Cách đo\nk6\n\n"
               "### Acceptance criteria\n- [ ] đạt")
        self.assertTrue(any("Nhóm" in e for e in templates.check_template(
            TPL, "Non-Functional Requirement", "[Non-Functional Requirement] Performance: p95 < 300ms", nfr)))
        self.assertTrue(any("Affects" in e for e in templates.check_template(
            TPL, "Bug", "[Bug] Giỏ hàng: sai tổng", "### Affects\nkhông có số\n\n### Các bước tái hiện\n1. a\n\n"
                                                   "### Kết quả mong đợi\na\n\n### Kết quả thực tế\nb")))

    def test_fill_builds_valid_task_body(self):
        body = templates.fill(TPL, "Task", {"Việc cần làm": "Thêm API POST /orders"})
        self.assertIn("### Definition of done\n- [ ] Test pass", body)
        self.assertEqual(templates.check_template(TPL, "Task", "[Task] Thêm API POST /orders", body), [])
        with self.assertRaisesRegex(RuleError, "không có mục"):
            templates.fill(TPL, "Task", {"Sai": "x"})

    def test_skeleton(self):
        sk = templates.skeleton(TPL, "Bug")
        self.assertTrue(sk.startswith("Title: [Bug] <Thành phần>: <triệu chứng>"))
        self.assertIn("### Các bước tái hiện", sk)

    def test_validate_plan_with_templates(self):
        plan = {"milestone": "v1", "items": [{"key": "E001", "type": "Epic", "title": "E", "children": []}]}
        errs = planning.validate_plan(WF, plan, TPL)
        self.assertTrue(any("E001: Title" in e for e in errs))
        self.assertTrue(any("E001: Thiếu mục '### Mục tiêu'" in e for e in errs))
        ok = {"milestone": "v1", "items": [{"key": "E001", "type": "Epic", "title": "Quản lý đơn hàng",
                                            "body": "### Mục tiêu\nx\n\n### Phạm vi\n- y"}]}
        self.assertEqual(planning.validate_plan(WF, ok, TPL), [])  # title không prefix: được thêm trước khi kiểm


PR_BODY = ("### Liên kết\nCloses #12\n\n### Thay đổi\n- thêm API\n\n### Kiểm thử\n- [x] check pass\n\n"
           "### Security\nKhông chạm security")


class TestPrTemplate(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(templates.check_pr(PR_TPL, "[Task] Thêm API POST /orders (#12)", PR_BODY), [])

    def test_option_then_trailing_text(self):
        body = PR_BODY + "\n\n🤖 Generated with [Claude Code](https://claude.com/claude-code)"
        self.assertEqual(templates.check_pr(PR_TPL, "[Task] Thêm API POST /orders (#12)", body), [])

    def test_invalid(self):
        errs = templates.check_pr(PR_TPL, "Thêm API", PR_BODY.replace("Closes #12", "liên quan task"))
        self.assertTrue(any("Title PR" in e for e in errs))
        self.assertTrue(any("Liên kết" in e for e in errs))
        self.assertTrue(templates.check_pr(PR_TPL, "[FR] X (#1)", PR_BODY))  # prefix viết tắt bị từ chối


if __name__ == "__main__":
    unittest.main()
