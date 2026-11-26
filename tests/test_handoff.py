import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from support import WF
from omi_hub.application import handoff
from omi_hub.domain import handoff as hd
from omi_hub.infrastructure.github.client import GhError

D = date(2026, 11, 26)


def item(n, type_, status, parent=None, title=None):
    return {"number": n, "type": type_, "status": status, "parent": parent, "title": title or f"[{type_}] {n}",
            "milestone": None, "blockers": [], "rework_count": 0, "blocked_reason": None, "open_blockers": 0, "priority": None, "milestone_due": None,
            "state": "CLOSED" if status in ("Done", "Cancelled") else "OPEN"}


class HGh:
    GhError = GhError
    AUDIT_TITLE = "OMI Audit"

    def __init__(self, items, fail=False):
        self.items, self.fail = items, fail

    def project_items(self, cfg):
        if self.fail:
            raise GhError("gh api: HTTP 502")
        return self.items

    def marked_comment(self, cfg, n, name):
        return (1, "<!-- omi:findings -->\n\n- [ ] Tách hàm (từ #5)") if n == 1 else (None, None)


class TestHandoff(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = {"_root": self.tmp.name}
        self.f = Path(self.tmp.name) / ".omi" / "HANDOFF.md"
        self.f.parent.mkdir()
        self.items = [item(1, "Epic", "In Progress"), item(2, "Functional Requirement", "In Progress", 1),
                      item(3, "Task", "Done", 2), item(4, "Task", "Ready", 2), item(6, "Task", "Draft", 2),
                      item(7, "Task", "In Progress", 2)]

    def tearDown(self):
        self.tmp.cleanup()

    def run_h(self, items=None, fail=False):
        with mock.patch.object(handoff, "gh", HGh(items or self.items, fail)), mock.patch("builtins.print") as pr:
            code = handoff.handoff(self.cfg, WF, D, doctor_summary=lambda cfg: "OK 8 · WARN 1 · FAIL 0")
        return code, [c.args[0] for c in pr.call_args_list]

    def test_ac144_1_auto_block_rewritten_rest_kept(self):
        self.f.write_text("# HANDOFF\nGhi tay của người dùng\n", encoding="utf-8")
        (Path(self.tmp.name) / ".omi" / "tmp").mkdir()
        (Path(self.tmp.name) / ".omi" / "tmp" / "current").write_text("7", encoding="utf-8")
        (Path(self.tmp.name) / ".omi" / "feedback-queue.jsonl").write_text('{"title":"a"}\n', encoding="utf-8")
        self.assertEqual(self.run_h()[0], 0)
        doc = self.f.read_text(encoding="utf-8")
        auto = hd.get_block(doc, hd.AUTO)
        for s in ("- Plugin: ", "- Doctor: OK 8 · WARN 1", "- Đang làm: #7 [Task] 7 — In Progress",
                  "- Ready kế tiếp: #4 [Task] 4", "(lần đầu, bỏ qua)", "  - #6 [Task] 6 — Draft",
                  "  - [1.1] Tách hàm (từ #5)", "- Hàng đợi feedback: 1 mục"):
            self.assertIn(s, auto)
        self.assertIn("Ghi tay của người dùng", doc)
        self.items[3]["status"] = "Done"  # #4 xong sau lần trước
        self.run_h()
        doc2 = self.f.read_text(encoding="utf-8")
        self.assertIn("- Done từ lần handoff trước:\n  - #4 [Task] 4 — Done", doc2)
        self.assertEqual(doc2.count(hd.AUTO[0]), 1)
        self.assertIn("Ghi tay của người dùng", doc2)

    def test_ac144_1_network_error_keeps_file(self):
        self.f.write_text("# HANDOFF\nx\n", encoding="utf-8")
        code, out = self.run_h(fail=True)
        self.assertEqual(code, 1)
        self.assertTrue(out[0].startswith("HANDOFF WARN"))
        self.assertEqual(self.f.read_text(encoding="utf-8"), "# HANDOFF\nx\n")

    def test_ac144_2_note_appends_dated_line(self):
        self.f.write_text("# HANDOFF\n\n## Ghi chú phiên\n- 2026-11-20: cũ #3\n\n## Khác\ny\n", encoding="utf-8")
        with mock.patch("builtins.print"):
            handoff.note(self.cfg, "PO chọn   phương án B cho #4", D)
        doc = self.f.read_text(encoding="utf-8")
        self.assertIn("## Ghi chú phiên\n- 2026-11-20: cũ #3\n- 2026-11-26: PO chọn phương án B cho #4\n\n## Khác", doc)
        self.f.unlink()
        with mock.patch("builtins.print"):
            handoff.note(self.cfg, "đầu tiên", D)
        self.assertIn("## Ghi chú phiên\n- 2026-11-26: đầu tiên", self.f.read_text(encoding="utf-8"))

    def test_ac144_3_prune_closed_and_old_notes(self):
        self.f.write_text("# HANDOFF\n\n## Ghi chú phiên\n- 2026-11-25: xong #3\n- 2026-11-25: còn #3 #4\n"
                          "- 2026-11-01: chung chung cũ\n- 2026-11-20: chung chung mới\n- 2026-11-01: #99 ngoài project\n",
                          encoding="utf-8")
        code, out = self.run_h()
        doc = self.f.read_text(encoding="utf-8")
        self.assertIn("(xoá 2 ghi chú cũ)", out[-1])
        self.assertNotIn("xong #3", doc)
        self.assertNotIn("chung chung cũ", doc)
        for s in ("còn #3 #4", "chung chung mới", "#99 ngoài project"):
            self.assertIn(s, doc)


if __name__ == "__main__":
    unittest.main()
