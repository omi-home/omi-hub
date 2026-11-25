import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import support  # noqa: F401  (sys.path)
from omi_hub.application import setup, workspace
from omi_hub.domain.text import BEGIN


class TestConfig(unittest.TestCase):
    def test_find_root_walks_up_and_repo_dir(self):
        with tempfile.TemporaryDirectory() as d:
            ws = Path(d)
            (ws / ".omi").mkdir()
            (ws / ".omi" / "project.json").write_text('{"repo_dir": "app"}', encoding="utf-8")
            (ws / "app" / "src").mkdir(parents=True)
            self.assertEqual(workspace.find_root(ws / "app" / "src"), ws.resolve())
            old = os.getcwd()
            os.chdir(ws / "app" / "src")
            try:
                cfg = workspace.load_cfg()
            finally:
                os.chdir(old)
            self.assertEqual(workspace.repo_dir(cfg).resolve(), (ws / "app").resolve())
            self.assertEqual(workspace.tmp_dir(cfg).resolve(), ws.resolve() / ".omi" / "tmp")

    def test_env_fallback_in_ci(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"OMI_CONFIG": '{"owner": "o"}'}):
            old = os.getcwd()
            os.chdir(d)
            try:
                cfg = workspace.load_cfg()
            finally:
                os.chdir(old)
            self.assertEqual((cfg["owner"], cfg["repo_dir"]), ("o", "."))


class TestWriteTemplates(unittest.TestCase):
    def test_writes_and_merges(self):
        with tempfile.TemporaryDirectory() as d:
            ws = Path(d)
            dest = ws / "app"  # repo là thư mục con của workspace
            dest.mkdir()
            (ws / "AGENTS.md").write_text("# Dự án X\n", encoding="utf-8")
            (ws / ".claude").mkdir()
            (ws / ".claude/settings.json").write_text('{"model": "opus"}', encoding="utf-8")
            setup.write_templates("acme/omi-hub", dest, ws)
            setup.write_templates("acme/omi-hub", dest, ws)  # chạy lại không nhân đôi
            agents = (ws / "AGENTS.md").read_text(encoding="utf-8")
            self.assertFalse((dest / "AGENTS.md").exists())
            self.assertFalse((dest / ".omi").exists())
            self.assertTrue(agents.startswith("# Dự án X"))
            self.assertEqual(agents.count(BEGIN), 1)
            forms = sorted(p.name for p in (dest / ".github/ISSUE_TEMPLATE").glob("*.yml"))
            self.assertEqual(forms, ["bug.yml", "change-request.yml", "config.yml", "epic.yml",
                                     "functional-requirement.yml", "non-functional-requirement.yml",
                                     "task.yml", "user-story.yml"])
            wf = (dest / ".github/workflows/omi-audit.yml").read_text(encoding="utf-8")
            self.assertIn("repository: acme/omi-hub", wf)
            self.assertNotIn("__OMI_HUB_REPO__", wf)
            pr_md = (dest / ".github/pull_request_template.md").read_text(encoding="utf-8")
            self.assertIn("### Liên kết", pr_md)
            self.assertIn("### Security", pr_md)
            self.assertLessEqual(len(agents.splitlines()), 20)  # giữ AGENTS.md ngắn: nạp vào mọi phiên
            settings = json.loads((ws / ".claude/settings.json").read_text(encoding="utf-8"))
            self.assertEqual(settings["model"], "opus")  # giữ cấu hình cũ
            self.assertEqual(settings["enabledPlugins"], {"omi-hub@omi-home": True})
            self.assertEqual(settings["extraKnownMarketplaces"]["omi-home"]["source"]["repo"], "acme/omi-hub")
            self.assertFalse((dest / ".claude").exists())

if __name__ == "__main__":
    unittest.main()
