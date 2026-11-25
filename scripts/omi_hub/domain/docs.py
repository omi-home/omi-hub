"""Tham chiếu tài liệu trong body issue (`### Tham chiếu`): parse và cắt đúng mục markdown — thuần, không I/O."""
import re

REF = re.compile(r"([\w./-]+\.md)(?:#([\w%-]+))?")
HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
FENCE = re.compile(r"^\s*(```|~~~)")


def doc_refs(body):
    """[(path, anchor|None)] trong mục `### Tham chiếu`, theo thứ tự, không trùng."""
    m = re.search(r"^### Tham chiếu\s*\n(.*?)(?=^### |\Z)", body or "", re.M | re.S)
    out = []
    for path, anchor in REF.findall(m.group(1) if m else ""):
        ref = (path, anchor or None)
        if ref not in out:
            out.append(ref)
    return out


def slug(text):
    """Anchor kiểu GitHub: chữ thường, bỏ dấu câu (giữ chữ có dấu), khoảng trắng → '-'."""
    return re.sub(r"[^\w\- ]", "", text.strip().lower()).replace(" ", "-")


def section(md, anchor):
    """Nội dung từ heading khớp anchor tới heading cùng cấp hoặc cao hơn; None nếu không có."""
    want, out, level, fenced = slug(anchor), [], None, False
    for line in md.splitlines():
        if FENCE.match(line):
            fenced = not fenced
        h = None if fenced else HEADING.match(line)
        if level is None:
            if h and slug(h.group(2)) == want:
                level = len(h.group(1))
                out.append(line)
        elif h and len(h.group(1)) <= level:
            break
        else:
            out.append(line)
    return "\n".join(out).strip() if level is not None else None


def render_refs(found, missing):
    """found: [(label, text)], missing: [label] → mục markdown ghép vào context."""
    parts = [f"## Tham chiếu {label}\n{text}" for label, text in found]
    parts += [f"⚠️ Tham chiếu không tìm thấy: {label}" for label in missing]
    return "\n\n".join(parts)

