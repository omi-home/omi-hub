"""Use case apply: tạo cây issue từ plan JSON, idempotent theo key."""
import json
from pathlib import Path

from omi_hub.application import items
from omi_hub.config import load_templates
from omi_hub.domain.errors import RuleError
from omi_hub.domain.planning import validate_plan
from omi_hub.infrastructure.github import gateway as gh

APPROVE_STATUS = {"Epic": "Approved", "User Story": "Approved", "Functional Requirement": "Approved", "Non-Functional Requirement": "Approved",
                  "Task": "Ready"}


def apply(cfg, wf, plan_path, approve=False):
    plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    errs = validate_plan(wf, plan, load_templates())
    if errs:
        raise RuleError(errs)
    keys = dict(gh.existing_keys(cfg))

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
    return keys
