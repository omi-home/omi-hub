"""Truy vấn chỉ đọc: cây work item, việc tiếp theo. Trả dữ liệu, CLI lo in."""
from omi_hub.domain.errors import RuleError
from omi_hub.domain.planning import pick_next
from omi_hub.domain.progress import render_status
from omi_hub.infrastructure.github import gateway as gh


def tree(cfg, n=None):
    """Một truy vấn project_items rồi dựng cây cục bộ; trả các dòng đã thụt lề."""
    items = [i for i in gh.project_items(cfg) if i["title"] != gh.AUDIT_TITLE]
    by = {i["number"]: i for i in items}
    kids = {}
    for i in items:
        kids.setdefault(i["parent"], []).append(i)
    lines = []

    def walk(i, indent):
        lines.append(f"{indent}#{i['number']} {i['title']} — {i['status']}")  # title đã có prefix loại
        for c in sorted(kids.get(i["number"], []), key=lambda x: x["number"]):
            walk(c, indent + "  ")

    if n is not None and n not in by:
        raise RuleError(f"#{n} không có trong Project")
    roots = [by[n]] if n is not None else sorted((i for i in items if i["parent"] not in by),
                                                 key=lambda x: x["number"])
    for r in roots:
        walk(r, "")
    return lines


def next_item(cfg, wf):
    return pick_next(wf, gh.project_items(cfg))


def status(cfg, wf, milestone=None):
    return render_status(wf, [i for i in gh.project_items(cfg) if i["title"] != gh.AUDIT_TITLE], milestone)
