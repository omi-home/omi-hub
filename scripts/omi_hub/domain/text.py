"""Helper text thuần: body issue, marker <!-- omi:... -->, merge AGENTS.md."""
import re

BEGIN, END = "<!-- omi:begin -->", "<!-- omi:end -->"
MARKER = re.compile(r"<!-- omi:(\S+?)(?:=(.*?))? -->")


def build_body(body, affects=(), key=None):
    parts = [body.strip()] if body.strip() else []
    if affects and "### Affects" not in body:
        parts.append("### Affects\n" + " ".join(f"#{n}" for n in affects))
    if key:
        parts.append(f"<!-- omi:key={key} -->")
    return "\n\n".join(parts)


def affected(body):
    m = re.search(r"^### Affects\s*\n(.+)$", body or "", re.M)
    return [int(x) for x in re.findall(r"#(\d+)", m.group(1))] if m else []


def find_marker(texts, name):
    found = None
    for t in texts:
        for m in MARKER.finditer(t or ""):
            if m.group(1) == name:
                found = m.group(2) if m.group(2) is not None else True
    return found


def merge_agents_md(existing, section):
    section = section.strip()
    if BEGIN in existing and END in existing:
        head, rest = existing.split(BEGIN, 1)
        _, tail = rest.split(END, 1)
        return head + section + tail
    return (existing.rstrip() + "\n\n" if existing.strip() else "") + section + "\n"
