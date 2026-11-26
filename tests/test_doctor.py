import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import support  # noqa: F401  (sys.path)
from omi_hub.application import doctor, setup
from omi_hub.config import load_workflow
from omi_hub.infrastructure.github.client import GhError

FIELDS = {"Status": {"id": "F", "options": {s: s for s in load_workflow()["statuses"]}}}


class FakeGh:
    GhError = GhError

    def __init__(self, cfg, latest=None, variable=None, secrets=("OMI_PROJECT_TOKEN",), default="develop",
                 ruleset=True, fields=FIELDS):
        self.latest = latest or json.loads(doctor.PLUGIN_JSON.read_text(encoding="utf-8"))["version"]
        self.variable = json.dumps({k: v for k, v in cfg.items() if not k.startswith("_")}) \
            if variable is None else variable
        self.secrets, self.default, self.ruleset, self.fields = set(secrets), default, ruleset, fields

    def remote_json(self, repo, path):
        return {"version": self.latest}

    def load_fields(self, owner, number):
        return self.fields

    def get_variable(self, cfg, name):
        if self.variable == "":
            raise GhError("variable OMI_CONFIG was not found")
        return self.variable

    def secret_names(self, cfg):
        return self.secrets

    def default_branch(self, owner, repo):
        return self.default

    def has_ruleset(self, cfg):
        return self.ruleset


class TestDoctor(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        ws = self.ws = Path(self.d.name)
        (ws / "app").mkdir()
        setup.write_templates("acme/omi-hub", ws / "app", ws)  # workspace vừa init xong
        self.cfg = {"owner": "o", "repo": "r", "repo_dir": "app", "project_number": 3, "project_id": "P",
                    "fields": FIELDS, "default_branch": "develop", "main_branch": "main",
                    "commands": {"test": "pytest"}, "_root": str(ws)}

    def tearDown(self):
        self.d.cleanup()

    def run_doctor(self, **kw):
        out = io.StringIO()
        with mock.patch.object(doctor, "gh", FakeGh(self.cfg, **kw)), contextlib.redirect_stdout(out):
            code = doctor.doctor(self.cfg)
        return code, out.getvalue().splitlines()

    def line(self, lines, name):
        return next(x for x in lines if x.split(" ", 1)[1].startswith(name))

    def test_ac94_1_one_line_per_check_and_exit_code(self):
        code, lines = self.run_doctor()
        self.assertEqual(code, 0)
        self.assertEqual(len(lines), 9)
        self.assertTrue(all(x.startswith("OK ") for x in lines), lines)
        code, lines = self.run_doctor(secrets=())
        self.assertEqual(code, 1)
        self.assertRegex(self.line(lines, "secret"), r"^FAIL secret: .+ → .+")

    def test_ac132_4_session_reminds_doctor_on_version_change(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hooks"))
        import guard
        plugin = doctor.PLUGIN_JSON.parents[1]
        ver = json.loads(doctor.PLUGIN_JSON.read_text(encoding="utf-8"))["version"]
        (self.ws / ".omi").mkdir(exist_ok=True)
        (self.ws / ".omi" / "project.json").write_text("{}", encoding="utf-8")
        self.assertIn(f"DOCTOR: plugin (chưa doctor) → {ver}, chạy OMI_CLI doctor",
                      guard.session_text(plugin, self.ws, "resume"))
        self.run_doctor(secrets=())  # FAIL → không ghi version
        self.assertFalse((self.ws / ".omi" / "doctor.json").exists())
        self.run_doctor()  # PASS → ghi version, hết nhắc
        self.assertNotIn("DOCTOR:", guard.session_text(plugin, self.ws, "resume"))
        (self.ws / ".omi" / "doctor.json").write_text('{"version": "0.0.1"}', encoding="utf-8")
        self.assertIn(f"DOCTOR: plugin 0.0.1 → {ver}", guard.session_text(plugin, self.ws, "resume"))

    def test_ac94_1_ruleset_missing_only_warns(self):
        code, lines = self.run_doctor(ruleset=False)
        self.assertEqual(code, 0)
        self.assertTrue(self.line(lines, "ruleset").startswith("WARN "))

    def test_ac94_2_plugin_version_behind(self):
        code, lines = self.run_doctor(latest="99.0.0")
        self.assertEqual(code, 1)
        self.assertIn("mới nhất 99.0.0", self.line(lines, "plugin version"))
        self.assertTrue(self.line(lines, "plugin version").startswith("FAIL"))

    def test_ac94_3_github_files_drift(self):
        wf = self.ws / "app/.github/workflows/omi-audit.yml"
        wf.write_bytes(wf.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))  # CRLF do autocrlf không tính là lệch
        self.assertTrue(self.line(self.run_doctor()[1], ".github").startswith("OK"))
        wf.write_text("cũ", encoding="utf-8")
        (self.ws / "app/.github/ISSUE_TEMPLATE/bug.yml").unlink()
        line = self.line(self.run_doctor()[1], ".github")
        self.assertIn("ISSUE_TEMPLATE/bug.yml", line)
        self.assertIn("workflows/omi-audit.yml", line)
        self.assertTrue(line.startswith("FAIL"))

    def test_ac94_4_settings_and_config(self):
        (self.ws / ".claude/settings.json").write_text('{"model": "opus"}', encoding="utf-8")
        self.cfg["commands"] = {}
        del self.cfg["main_branch"]
        old = {"Status": {"id": "F", "options": {s: s for s in load_workflow()["statuses"] if s != "Waiting"}}}
        self.cfg["fields"] = old
        _, lines = self.run_doctor(fields=old)
        self.assertIn("thiếu option Waiting", self.line(lines, "fields"))
        self.cfg["fields"] = FIELDS
        code, lines = self.run_doctor(fields={"Status": {"id": "OTHER"}})
        self.assertEqual(code, 1)
        self.assertIn("omi-hub@omi-home", self.line(lines, "settings.json"))
        self.assertIn("main_branch", self.line(lines, "project.json"))
        self.assertTrue(self.line(lines, "fields").startswith("FAIL"))

    def test_ac94_5_github_settings(self):
        code, lines = self.run_doctor(variable="", secrets=(), default="main")
        self.assertEqual(code, 1)
        for name in ("OMI_CONFIG", "secret", "default branch"):
            self.assertTrue(self.line(lines, name).startswith("FAIL"), name)
        stale = self.run_doctor(variable='{"owner": "o"}')[1]
        self.assertTrue(self.line(stale, "OMI_CONFIG").startswith("FAIL"))


if __name__ == "__main__":
    unittest.main()
