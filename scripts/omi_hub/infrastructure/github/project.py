"""Project v2: đọc items, ghi field, thêm item."""
import time

from . import client
from .nodes import field_value, type_name

FIELD_KINDS = {"Status": "single", "Priority": "single", "Estimate": "number",
               "Rework Count": "number", "Blocked Reason": "text"}

ITEMS_QUERY = """
query($id: ID!, $after: String) {
  node(id: $id) { ... on ProjectV2 { items(first: 100, after: $after) {
    pageInfo { hasNextPage endCursor }
    nodes { id
      status: fieldValueByName(name: "Status") { ... on ProjectV2ItemFieldSingleSelectValue { name } }
      priority: fieldValueByName(name: "Priority") { ... on ProjectV2ItemFieldSingleSelectValue { name } }
      rework: fieldValueByName(name: "Rework Count") { ... on ProjectV2ItemFieldNumberValue { number } }
      blocked: fieldValueByName(name: "Blocked Reason") { ... on ProjectV2ItemFieldTextValue { text } }
      content { ... on Issue { id number title state stateReason issueType { name }
        milestone { title dueOn } parent { number } blockedBy(first: 50) { nodes { number state } } } }
    } } } }
}"""


def normalize_project_item(node):
    c = node.get("content") or {}
    if "number" not in c:
        return None  # draft issue hoặc PR
    ms = c.get("milestone") or {}
    return {
        "item_id": node["id"], "id": c["id"], "number": c["number"], "title": c["title"],
        "type": type_name(c), "state": c["state"], "state_reason": c.get("stateReason"),
        "status": field_value(node, "status", "name"), "priority": field_value(node, "priority", "name"),
        "rework_count": int(field_value(node, "rework", "number") or 0),
        "blocked_reason": field_value(node, "blocked", "text"),
        "milestone": ms.get("title"), "milestone_due": ms.get("dueOn"),
        "parent": (c.get("parent") or {}).get("number"),
        "blockers": (blockers := [b["number"] for b in c["blockedBy"]["nodes"] if b["state"] == "OPEN"]),
        "open_blockers": len(blockers),
        "in_project": True,
    }


def project_items(cfg):
    out, after = [], None
    while True:
        page = client.graphql(ITEMS_QUERY, id=cfg["project_id"], after=after)["node"]["items"]
        out += [i for i in map(normalize_project_item, page["nodes"]) if i]
        if not page["pageInfo"]["hasNextPage"]:
            return out
        after = page["pageInfo"]["endCursor"]


SET_FIELD = """mutation($project: ID!, $item: ID!, $field: ID!, $value: ProjectV2FieldValue!) {
  updateProjectV2ItemFieldValue(input: {projectId: $project, itemId: $item, fieldId: $field, value: $value}) {
    projectV2Item { id } } }"""
CLEAR_FIELD = """mutation($project: ID!, $item: ID!, $field: ID!) {
  clearProjectV2ItemFieldValue(input: {projectId: $project, itemId: $item, fieldId: $field}) {
    projectV2Item { id } } }"""
ADD_ITEM = """mutation($project: ID!, $content: ID!) {
  addProjectV2ItemById(input: {projectId: $project, contentId: $content}) { item { id } } }"""


def set_field(cfg, item_id, field, value):
    f, kind = cfg["fields"][field], FIELD_KINDS[field]
    if kind == "single":
        if value not in f["options"]:
            raise client.GhError(f"Field {field} không có option '{value}'")
        val = {"singleSelectOptionId": f["options"][value]}
    elif kind == "number":
        val = {"number": float(value)}
    else:
        val = {"text": str(value)}
    client.graphql(SET_FIELD, project=cfg["project_id"], item=item_id, field=f["id"], value=val)


def clear_field(cfg, item_id, field):
    client.graphql(CLEAR_FIELD, project=cfg["project_id"], item=item_id, field=cfg["fields"][field]["id"])


FIND_ITEM = """query($id: ID!) { node(id: $id) { ... on Issue {
  projectItems(first: 10) { nodes { id project { id } } } } } }"""


def find_item(cfg, node_id):
    nodes = client.graphql(FIND_ITEM, id=node_id)["node"]["projectItems"]["nodes"]
    return next((x["id"] for x in nodes if x["project"]["id"] == cfg["project_id"]), None)


def add_to_project(cfg, node_id):
    """GitHub tự thêm sub-issue của item đã trong Project (bất đồng bộ) → add báo 'already exists': tìm lại item."""
    for _ in range(6):
        try:
            return client.graphql(ADD_ITEM, project=cfg["project_id"], content=node_id)["addProjectV2ItemById"]["item"]["id"]
        except client.GhError as e:
            if "already exists" not in str(e):
                raise
        item = find_item(cfg, node_id)
        if item:
            return item
        time.sleep(2)
    raise client.GhError(f"Không lấy được item Project cho {node_id}")
