"""Render text cho agent/PR: context task, cây plan, title/body PR."""
from .acceptance import ac_section, parse_ac
from .planning import AC_TYPES
from .text import MARKER


GENERATED = ("-lock.json", ".lock", "/pnpm-lock.yaml", "/packages.lock.json")


def filter_diff(diff_lines):
    """Bỏ khối diff của lockfile/file sinh; trả (dòng còn lại, tên file đã bỏ)."""
    kept, dropped, skip = [], [], False
    for line in diff_lines:
        if line.startswith("diff --git "):
            name = line.rsplit(" b/", 1)[-1]
            skip = ("/" + name).endswith(GENERATED)
            if skip:
                dropped.append(name)
        if not skip:
            kept.append(line)
    return kept, dropped


def tail(text, n=60):
    return "\n".join((text or "").rstrip().splitlines()[-n:])


def strip_markers(body):
    return MARKER.sub("", body or "").strip()


def render_context(s, parent=None, affects=()):
    out = [f"# #{s['number']} {s['title']} — {s['status']}", strip_markers(s["body"])]
    for label, x in ([("Parent", parent)] if parent else []) + [("Affects", a) for a in affects]:
        out += [f"## {label} #{x['number']} {x['title']}",
                "### Acceptance criteria\n" + (ac_section(x["body"]) or "(không có)")]
    if parent and parent["type"] in AC_TYPES:
        p = parent["number"]
        out.append(f"## Quy ước\nAC thứ i của #{p} (trừ [manual]) ↔ test có tên chứa `ac{p}_<i>`. Kiểm tra: `check`.")
    return "\n\n".join(x for x in out if x)


def render_plan(plan):
    lines = []

    def walk(node, depth):
        ac = f" (AC:{len(parse_ac(node.get('body', '')))})" if node["type"] in AC_TYPES else ""
        dep = " ⛔ " + ", ".join(f"#{b}" if isinstance(b, int) else b for b in node["blocked_by"]) \
            if node.get("blocked_by") else ""
        lines.append(f"{'  ' * depth}{node['key']} [{node['type']}] {node['title']}{ac}{dep}")
        for c in node.get("children", []):
            walk(c, depth + 1)

    for node in plan["items"]:
        walk(node, 0)
    return "\n".join(lines)


def pr_title(s):
    return f"{s['title']} (#{s['number']})"


def render_pr_body(s, parent, commits, security):
    link = f"Closes #{s['number']}" + (f"\nParent: #{parent['number']} {parent['title']}" if parent else "")
    acs = parse_ac(parent["body"]) if parent and parent["type"] in AC_TYPES else []
    parts = [("Liên kết", link), ("Thay đổi", "\n".join(f"- {c}" for c in commits) or "- (xem commit)")]
    if acs:
        parts.append(("Acceptance criteria liên quan", "\n".join(
            f"- AC{a['i']}: {a['text']}" + ("" if a["manual"] else f" → test `ac{parent['number']}_{a['i']}`")
            for a in acs)))
    parts += [("Kiểm thử", "- [x] lint/typecheck/scan/test pass (`check`)\n- [ ] CI xanh (`qa` kiểm)"),
              ("Security", "Có chạm security" if security else "Không chạm security")]
    return "\n\n".join(f"### {h}\n{v}" for h, v in parts)
