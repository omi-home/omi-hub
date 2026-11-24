"""Đọc/ghi issue: snapshot đầy đủ ngữ cảnh cho guard."""
from . import client
from .nodes import field_value, in_project, status_of, type_name

AUDIT_TITLE = "OMI Audit"

_ITEM_FIELDS = """
  status: fieldValueByName(name: "Status") { ... on ProjectV2ItemFieldSingleSelectValue { name } }
  rework: fieldValueByName(name: "Rework Count") { ... on ProjectV2ItemFieldNumberValue { number } }
  blocked: fieldValueByName(name: "Blocked Reason") { ... on ProjectV2ItemFieldTextValue { text } }
"""
_STATUS_ONLY = 'projectItems(first: 10) { nodes { id project { id } status: fieldValueByName(name: "Status") { ... on ProjectV2ItemFieldSingleSelectValue { name } } } }'

SNAPSHOT_QUERY = f"""
query($owner: String!, $repo: String!, $number: Int!) {{
  repository(owner: $owner, name: $repo) {{
    issue(number: $number) {{
      id number title body state stateReason
      issueType {{ name }}
      milestone {{ title }}
      labels(first: 20) {{ nodes {{ name }} }}
      parent {{ number issueType {{ name }} {_STATUS_ONLY} }}
      subIssues(first: 100) {{ nodes {{ number title state issueType {{ name }} {_STATUS_ONLY} }} }}
      blockedBy(first: 50) {{ nodes {{ number state }} }}
      closedByPullRequestsReferences(first: 10, includeClosedPrs: true) {{ nodes {{ number state merged }} }}
      projectItems(first: 10) {{ nodes {{ id project {{ id }} {_ITEM_FIELDS} }} }}
    }}
  }}
}}"""


def normalize_issue(raw, project_id):
    it = in_project(raw["projectItems"]["nodes"], project_id)
    p = raw.get("parent")
    return {
        "id": raw["id"], "number": raw["number"], "title": raw["title"], "body": raw["body"],
        "type": type_name(raw), "state": raw["state"], "state_reason": raw.get("stateReason"),
        "milestone": (raw.get("milestone") or {}).get("title"),
        "labels": [x["name"] for x in (raw.get("labels") or {}).get("nodes", [])],
        "item_id": it["id"] if it else None,
        "status": field_value(it, "status", "name"),
        "rework_count": int(field_value(it, "rework", "number") or 0),
        "blocked_reason": field_value(it, "blocked", "text"),
        "parent": ({"number": p["number"], "type": type_name(p), "status": status_of(p, project_id)} if p else None),
        "children": [{"number": c["number"], "title": c.get("title"), "type": type_name(c), "state": c["state"],
                      "status": status_of(c, project_id)} for c in raw["subIssues"]["nodes"]],
        "open_blockers": sum(1 for b in raw["blockedBy"]["nodes"] if b["state"] == "OPEN"),
        "prs": [{"number": x["number"], "state": x["state"], "merged": x["merged"]}
                for x in raw["closedByPullRequestsReferences"]["nodes"]],
    }


def issue_snapshot(cfg, number):
    d = client.graphql(SNAPSHOT_QUERY, owner=cfg["owner"], repo=cfg["repo"], number=number)
    raw = d["repository"]["issue"]
    if raw is None:
        raise client.GhError(f"Không tìm thấy issue #{number}")
    return normalize_issue(raw, cfg["project_id"])
