"""Đọc/ghi issue: snapshot đầy đủ ngữ cảnh cho guard."""
import json
import re

from . import client, milestones
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


def create_issue(cfg, title, body, type_, milestone=None):
    data = {"title": title, "body": body, "type": type_}
    if milestone:
        data["milestone"] = milestones.milestone_number(cfg, milestone)
    return client.rest("POST", f"{client.repo_path(cfg)}/issues", data)


def issue_db_id(cfg, n):
    return client.rest("GET", f"{client.repo_path(cfg)}/issues/{n}")["id"]


def add_sub_issue(cfg, parent_n, child_db_id):
    client.rest("POST", f"{client.repo_path(cfg)}/issues/{parent_n}/sub_issues", {"sub_issue_id": child_db_id})


def add_blocked_by(cfg, n, blocker_db_id):
    client.rest("POST", f"{client.repo_path(cfg)}/issues/{n}/dependencies/blocked_by", {"issue_id": blocker_db_id})


def blocker_numbers(cfg, n):
    q = """query($owner: String!, $repo: String!, $number: Int!) {
      repository(owner: $owner, name: $repo) { issue(number: $number) { blockedBy(first: 100) { nodes { number } } } } }"""
    d = client.graphql(q, owner=cfg["owner"], repo=cfg["repo"], number=n)
    return [b["number"] for b in d["repository"]["issue"]["blockedBy"]["nodes"]]


def comment(cfg, n, body):
    client.rest("POST", f"{client.repo_path(cfg)}/issues/{n}/comments", {"body": body})


def comments(cfg, n):
    pages = json.loads(client.run(["api", "--paginate", "--slurp", f"{client.repo_path(cfg)}/issues/{n}/comments?per_page=100"]))
    return [c["body"] for page in pages for c in page]


def close(cfg, n, reason):
    path = f"{client.repo_path(cfg)}/issues/{n}"
    try:
        client.rest("PATCH", path, {"state": "closed", "state_reason": reason})
    except client.GhError:
        # E2E: PATCH trả 422 dù issue đã đóng (nguyên nhân chưa xác định) → chỉ lỗi thật khi issue vẫn mở
        if (client.rest("GET", path) or {}).get("state") != "closed":
            raise


def assign_self(cfg, n):
    client.run(["issue", "edit", str(n), "-R", client.repo_full(cfg), "--add-assignee", "@me"])


def repo_issues(cfg):
    # ponytail: tối đa 1000 issue; chuyển sang phân trang GraphQL khi repo lớn hơn
    return json.loads(client.run(["issue", "list", "-R", client.repo_full(cfg), "--state", "all", "--limit", "1000",
                           "--json", "number,title,state"]))


def existing_keys(cfg):
    out = json.loads(client.run(["issue", "list", "-R", client.repo_full(cfg), "--state", "all", "--limit", "1000",
                          "--json", "number,title,body"]))
    keys = {}
    for i in out:
        m = re.search(r"<!-- omi:key=(\S+) -->", i["body"] or "")
        if m:
            keys[m.group(1)] = {"number": i["number"], "title": i["title"]}
    return keys


def upsert_audit_issue(cfg, body):
    found = [i for i in repo_issues(cfg) if i["title"] == AUDIT_TITLE and i["state"] == "OPEN"]
    if body is None:
        for i in found:
            close(cfg, i["number"], "completed")
    elif found:
        client.rest("PATCH", f"{client.repo_path(cfg)}/issues/{found[0]['number']}", {"body": body})
    else:
        client.rest("POST", f"{client.repo_path(cfg)}/issues", {"title": AUDIT_TITLE, "body": body})
