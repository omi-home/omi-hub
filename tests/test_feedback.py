import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import support  # noqa: F401  (sys.path tới scripts/)
from omi_hub.application import feedback
from omi_hub.infrastructure.github.client import GhError


class HubGh:
    GhError = GhError

    def __init__(self):
        self.issues, self.notes, self.fail, self.created = {}, {}, False, []

    def open_issue_by_title(self, cfg, title):
        if self.fail:
            raise GhError("gh api: HTTP 502")
        return next((n for n, t in self.issues.items() if t == title), None)

    def create_issue(self, cfg, title, body, type_, labels=None):
        n = 10 + len(self.issues)
        self.issues[n] = title
        self.created.append((cfg, title, body, type_, labels))
        return {"number": n}

    def comment(self, cfg, n, body):
        self.notes.setdefault(n, []).append(body)


class TestFeedback(unittest.TestCase):
    def setUp(self):
        self.g = HubGh()
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = {"owner": "o", "repo": "app", "_root": self.tmp.name}
        self.q = Path(self.tmp.name) / ".omi" / "feedback-queue.jsonl"
        self.p = mock.patch.object(feedback, "gh", self.g)
        self.p.start()

    def tearDown(self):
        self.p.stop()
        self.tmp.cleanup()

    def run_fb(self, *a, **k):
        with mock.patch("builtins.print") as pr:
            feedback.feedback(self.cfg, *a, **k)
        return [c.args[0] for c in pr.call_args_list]

    def test_ac139_1_creates_issue_in_plugin_repo(self):
        hub, ver = feedback.plugin_info()
        self.assertEqual(hub, {"owner": "omi-home", "repo": "omi-hub"})
        self.assertEqual(self.run_fb("Thiếu lệnh xoá label", body="chi tiết", kind="bug", cmd="edit"), ["FEEDBACK #10"])
        cfg, title, body, type_, labels = self.g.created[0]
        self.assertEqual((cfg, title, labels), (hub, "Thiếu lệnh xoá label", ["omi-feedback"]))
        for s in ("`o/app`", f"Plugin: {ver}", "Loại: bug", "Lệnh liên quan: edit", "chi tiết"):
            self.assertIn(s, body)

    def test_ac139_2_duplicate_title_comments_plus_one(self):
        self.g.issues[7] = "Thiếu lệnh xoá label"
        self.assertEqual(self.run_fb("Thiếu lệnh xoá label"), ["FEEDBACK #7 (trùng)"])
        self.assertEqual(self.g.created, [])
        self.assertIn("+1 từ `o/app`", self.g.notes[7][0])

    def test_ac139_3_queue_on_error_and_resend(self):
        self.g.fail = True
        out = self.run_fb("A")
        self.assertTrue(out[0].startswith("FEEDBACK QUEUED"), out)
        self.assertEqual(json.loads(self.q.read_text(encoding="utf-8"))["title"], "A")
        self.g.fail = False
        out = self.run_fb("B")  # lần feedback sau gửi lại hàng đợi trước
        self.assertEqual(out, ["FEEDBACK #10 (từ hàng đợi)", "FEEDBACK #11"])
        self.assertFalse(self.q.exists())
        self.g.fail = True
        self.run_fb("C")
        self.g.fail = False
        with mock.patch("builtins.print"):
            self.assertEqual(feedback.flush(self.cfg), 1)  # doctor gọi flush
        self.assertEqual(self.g.issues[12], "C")


if __name__ == "__main__":
    unittest.main()
