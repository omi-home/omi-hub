"""Findings review mang theo: 1 comment `<!-- omi:findings -->` trên parent, mỗi dòng `- [ ]`/`- [x]`.

Mã finding `<p>.<i>`: p = số issue giữ comment, i = thứ tự dòng (1-based, tính cả dòng đã xong → mã ổn định).
"""
import re

from .errors import RuleError

NAME = "findings"
HEAD = f"<!-- omi:{NAME} -->\n📌 Findings mang theo (làm khi sửa file liên quan, báo bằng `submit --findings`)"
LINE = re.compile(r"^- \[( |x)\] (.+)$", re.M)
SOURCE = re.compile(r"\s*\((?:từ|xong ở|chuyển từ|chuyển lên) #\d+[^)]*\)\s*$")


def parse(body):
    return [(m.group(1) == "x", m.group(2).strip()) for m in LINE.finditer(body or "")]


def render(items):
    return "\n".join([HEAD, ""] + [f"- [{'x' if done else ' '}] {text}" for done, text in items])


def _core(text):
    while SOURCE.search(text):
        text = SOURCE.sub("", text)
    return " ".join(text.split()).casefold()


def add(items, text, note):
    """Thêm `text (note)`; bỏ qua nếu đã có dòng cùng nội dung (không tính nguồn/trạng thái)."""
    text = " ".join(text.split())
    if not text or any(_core(t) == _core(text) for _, t in items):
        return items, False
    return items + [(False, f"{text} ({note})")], True


def mark(items, idx, note):
    """Đánh dấu xong các dòng (1-based) kèm `(note)`."""
    return [(True, f"{t} ({note})") if i in idx and not done else (done, t)
            for i, (done, t) in enumerate(items, 1)]


DONE_NOTE = re.compile(r"\s*\(xong ở #\d+\)$")


def reopen(items, idx):
    """Mở lại các dòng (1-based) đã đánh dấu xong nhầm: bỏ `[x]` và ghi chú `(xong ở #n)` cuối dòng."""
    return [(False, DONE_NOTE.sub("", t)) if i in idx and done else (done, t)
            for i, (done, t) in enumerate(items, 1)]


def parse_codes(raw):
    """'12.1,12.3' → {12: {1, 3}}; RuleError nếu sai dạng."""
    out = {}
    for c in filter(None, (x.strip() for x in raw.split(","))):
        m = re.fullmatch(r"(\d+)\.(\d+)", c)
        if not m:
            raise RuleError(f"Mã finding sai dạng: '{c}' (cần <p>.<i>)")
        out.setdefault(int(m.group(1)), set()).add(int(m.group(2)))
    return out


def open_codes(p, items):
    return [(f"{p}.{i}", t) for i, (done, t) in enumerate(items, 1) if not done]

