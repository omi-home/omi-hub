import unittest

import support  # noqa: F401  (sys.path)
from omi_hub.config import load_pr_template, load_templates
from omi_hub.domain import forms


class TestForms(unittest.TestCase):
    def test_render_form(self):
        tpl = load_templates()
        nfr = forms.render_form("Non-Functional Requirement", tpl["Non-Functional Requirement"])
        self.assertIn('type: "Non-Functional Requirement"', nfr)
        self.assertIn("type: dropdown", nfr)
        self.assertIn('label: "Cách đo"', nfr)
        self.assertIn('title: "[Functional Requirement] Hệ thống phải "', forms.render_form("Functional Requirement", tpl["Functional Requirement"]))
        self.assertIn('title: "[Epic] "', forms.render_form("Epic", tpl["Epic"]))
        self.assertIn("type: input", forms.render_form("Bug", tpl["Bug"]))
        self.assertEqual(forms.form_filename("User Story"), "user-story.yml")

    def test_render_pr_template(self):
        md = forms.render_pr_template(load_pr_template())
        self.assertTrue(md.startswith("<!-- Title:"))
        self.assertIn("<!-- chọn một: Không chạm security | Có chạm security -->", md)

if __name__ == "__main__":
    unittest.main()
