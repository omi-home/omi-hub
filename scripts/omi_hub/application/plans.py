"""Use case apply: tạo cây issue từ plan JSON, idempotent theo key."""
import json
from pathlib import Path

from omi_hub.application import items
from omi_hub.config import load_templates
from omi_hub.domain.errors import RuleError
from omi_hub.domain.lifecycle import WAITING
from omi_hub.domain.planning import validate_plan
from omi_hub.domain.templates import with_prefix
from omi_hub.infrastructure.github import gateway as gh

APPROVE_STATUS = {"Epic": "Approved", "User Story": "Approved", "Functional Requirement": "Approved", "Non-Functional Requirement": "Approved",
                  "Task": "Ready"}


def apply(cfg, wf, plan_path, approve=False):
    plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    tpl = load_templates()
    errs = validate_plan(wf, plan, tpl)
    if errs:
        raise RuleError(errs)
    found = gh.existing_keys(cfg)

    def walk(node):
        yield node
        for c in node.get("children", []):
            yield from walk(c)
    nodes = [x for n in plan["items"] for x in walk(n)]
    known = {x["key"] for x in nodes} | set(found)
    errs = []
    for node in nodes:
        old = found.get(node["key"])
        if old and old["title"] != with_prefix(tpl, node["type"], node["title"]):
            errs.append(f"key {node['key']} đã là #{old['number']} '{old['title']}' — đổi key hoặc sửa title cho khớp")
        errs += [f"{node['key']}: blocked_by key '{b}' không có trong plan hay repo"
                 for b in node.get("blocked_by", []) if isinstance(b, str) and b not in known]
    if errs:  # trước khi tạo gì: key trùng plan khác sẽ gắn nhầm cả cây con
        raise RuleError(errs)
    keys = {k: v["number"] for k, v in found.items()}
    for m in {n.get("milestone") or plan.get("milestone") for n in plan["items"] if "parent" not in n} - {None}:
        gh.ensure_milestone(cfg, m)  # node con kế thừa milestone parent, chỉ node gốc cần

    def create(node, parent):
        n = keys.get(node["key"])
        if n is None:
            top = parent is None
            n = items.new_item(cfg, wf, node["type"], node["title"], parent=parent,
                        affects=node.get("affects", []),
                        milestone=(node.get("milestone") or plan.get("milestone")) if top else None,
                        priority=node.get("priority"), estimate=node.get("estimate"),
                        body=node.get("body", ""), key=node["key"],
                        status=APPROVE_STATUS.get(node["type"]) if approve else None)
            keys[node["key"]] = n
        for c in node.get("children", []):
            create(c, n)

    for node in plan["items"]:
        create(node, node.get("parent"))

    # Sau khi cả cây đã có số: thêm quan hệ còn thiếu (chạy lại apply bổ sung được cho issue cũ).
    for node in nodes:
        refs = node.get("blocked_by", [])
        if not refs:
            continue
        n = keys[node["key"]]
        have = set(gh.blocker_numbers(cfg, n))
        for b in refs:
            bn = keys[b] if isinstance(b, str) else b
            if bn not in have:
                gh.add_blocked_by(cfg, n, gh.issue_db_id(cfg, bn))
                have.add(bn)
                print(f"#{n} blocked by #{bn}")
        s = gh.issue_snapshot(cfg, n)
        if s["status"] == "Ready" and s["open_blockers"]:
            items.move(cfg, wf, n, WAITING)
    return keys
