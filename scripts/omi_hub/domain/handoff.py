"""HANDOFF.md: mục tự động giữa marker + ghi chú phiên có vòng đời — thuần, không I/O."""
import re
from datetime import date, timedelta

AUTO = ("<!-- omi:handoff:auto -->", "<!-- /omi:handoff:auto -->")
NOTES = "## Ghi chú phiên"
NOTE_MAX_AGE = 14  # ngày, cho ghi chú không có #n
_DONE = re.compile(r"<!-- omi:handoff:done=([\d,]*) -->")
_NOTE = re.compile(r"^- (\d{4}-\d{2}-\d{2}): (.*)$")


def get_block(doc, marks):
    b, e = marks
    i, j = doc.find(b), doc.find(e)
    return doc[i + len(b):j].strip("\n") if 0 <= i < j else None


def put_block(doc, marks, content):
    """Thay nội dung giữa marker; chưa có thì chèn sau dòng tiêu đề `# ...` đầu file (hoặc đầu file)."""
    b, e = marks
    block = f"{b}\n{content.strip()}\n{e}"
    i, j = doc.find(b), doc.find(e)
    if 0 <= i < j:
        return doc[:i] + block + doc[j + len(e):]
    m = re.match(r"# .*\n", doc)
    k = m.end() if m else 0
    return (doc[:k] + ("\n" if k else "") + block + "\n\n" + doc[k:].lstrip("\n")).rstrip("\n") + "\n"


def done_seen(doc):
    """Các số Done đã ghi ở lần handoff trước; None nếu chưa từng chạy."""
    m = _DONE.search(get_block(doc, AUTO) or "")
    return None if m is None else {int(x) for x in m.group(1).split(",") if x}


def render_auto(version, doctor, current, nxt, new_done, pending, open_findings, queue, done_all, now):
    def lst(xs):
        return "\n".join(f"  - {x}" for x in xs) or "  - (không có)"
    return "\n".join([
        f"_Tự động bởi `OMI_CLI handoff` lúc {now} — không sửa tay mục này._",
        f"- Plugin: {version}",
        f"- Doctor: {doctor}",
        f"- Đang làm: {current or '(không có)'}",
        f"- Ready kế tiếp: {nxt or '(không có)'}",
        "- Done từ lần handoff trước:" + ("\n" + lst(new_done) if new_done is not None else " (lần đầu, bỏ qua)"),
        "- Chờ duyệt (Draft/Triage):\n" + lst(pending),
        "- Findings mở:\n" + lst(open_findings),
        f"- Hàng đợi feedback: {queue} mục" + (" — chạy `OMI_CLI doctor` để gửi lại" if queue else ""),
        f"<!-- omi:handoff:done={','.join(str(n) for n in sorted(done_all))} -->",
    ])


def _notes_span(lines):
    """(đầu, cuối) chỉ số dòng của mục ghi chú phiên (không gồm tiêu đề); None nếu chưa có."""
    try:
        i = lines.index(NOTES)
    except ValueError:
        return None
    j = next((k for k in range(i + 1, len(lines)) if lines[k].startswith(("## ", "<!-- omi:"))), len(lines))
    return i + 1, j


def add_note(doc, text, today):
    lines = doc.rstrip("\n").split("\n") if doc.strip() else []
    span = _notes_span(lines)
    if span is None:
        lines += ["", NOTES]
        span = (len(lines), len(lines))
    a, b = span
    while b > a and not lines[b - 1].strip():
        b -= 1
    lines.insert(b, f"- {today.isoformat()}: {' '.join(text.split())}")
    return "\n".join(lines) + "\n"


def prune_notes(doc, closed, today, max_age=NOTE_MAX_AGE):
    """Bỏ ghi chú mà mọi #n đã đóng, và ghi chú không có #n cũ hơn max_age ngày. Trả (doc, số dòng xoá)."""
    lines = doc.split("\n")
    span = _notes_span(lines)
    if span is None:
        return doc, 0
    a, b = span
    keep, removed = [], 0
    for line in lines[a:b]:
        m = _NOTE.match(line)
        if m:
            refs = {int(x) for x in re.findall(r"#(\d+)", m.group(2))}
            old = date.fromisoformat(m.group(1)) < today - timedelta(days=max_age)
            if (refs and refs <= closed) or (not refs and old):
                removed += 1
                continue
        keep.append(line)
    return "\n".join(lines[:a] + keep + lines[b:]), removed
