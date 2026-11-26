"""Findings review mang theo: 1 comment `<!-- omi:findings -->` trên parent, mỗi dòng `- [ ]`/`- [x]`.

Mã finding `<p>.<i>`: p = số issue giữ comment, i = thứ tự dòng (1-based, tính cả dòng đã xong → mã ổn định).
"""
import re

NAME = "findings"
HEAD = f"<!-- omi:{NAME} -->\n📌 Findings mang theo (làm khi sửa file liên quan, báo bằng `submit --findings`)"
LINE = re.compile(r"^- \[( |x)\] (.+)$", re.M)
SOURCE = re.compile(r"\s*\((?:từ|xong ở) #\d+[^)]*\)\s*$")


def parse(body):
    return [(m.group(1) == "x", m.group(2).strip()) for m in LINE.finditer(body or "")]


def render(items):
    return "\n".join([HEAD, ""] + [f"- [{'x' if done else ' '}] {text}" for done, text in items])


def _core(text):
    while SOURCE.search(text):
        text = SOURCE.sub("", text)
    return " ".join(text.split()).casefold()


def add(items, text, src):
    """Thêm `text (từ #src)`; bỏ qua nếu đã có dòng cùng nội dung (không tính nguồn/trạng thái)."""
    text = " ".join(text.split())
    if not text or any(_core(t) == _core(text) for _, t in items):
        return items, False
    return items + [(False, f"{text} (từ #{src})")], True


def open_codes(p, items):
    return [(f"{p}.{i}", t) for i, (done, t) in enumerate(items, 1) if not done]

