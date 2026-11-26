"""Truy vấn chỉ đọc: cây work item, việc tiếp theo. Trả dữ liệu, CLI lo in."""
from omi_hub.domain import findings
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
        dep = " ⛔ " + ", ".join(f"#{b}" for b in i["blockers"]) if i.get("blockers") else ""
        lines.append(f"{indent}#{i['number']} {i['title']} — {i['status']}{dep}")  # title đã có prefix loại
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
    its = [i for i in gh.project_items(cfg) if i["title"] != gh.AUDIT_TITLE]
    # ponytail: 1 lần đọc comment mỗi Epic Done; lọc theo milestone/thời gian nếu số Epic lớn
    left = {}
    for e in its:
        if e["type"] == "Epic" and e["status"] == "Done" and (milestone is None or e["milestone"] == milestone):
            codes = findings.open_codes(e["number"], findings.parse(gh.marked_comment(cfg, e["number"], findings.NAME)[1]))
            if codes:
                left[e["number"]] = codes
    return render_status(wf, its, milestone, left)
