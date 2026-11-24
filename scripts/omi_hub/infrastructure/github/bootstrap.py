"""Khởi tạo: Issue Types, Project, fields, label, variable."""
import json

from . import client, project

STATUS_COLORS = {"Draft": "GRAY", "Triage": "PINK", "Approved": "PURPLE", "Ready": "BLUE",
                 "In Progress": "YELLOW", "In Review": "ORANGE", "In QA": "ORANGE",
                 "Blocked": "RED", "Done": "GREEN", "Cancelled": "GRAY"}
UPDATE_STATUS = """mutation($field: ID!, $options: [ProjectV2SingleSelectFieldOptionInput!]) {
  updateProjectV2Field(input: {fieldId: $field, singleSelectOptions: $options}) {
    projectV2Field { ... on ProjectV2SingleSelectField { id } } } }"""


def current_repo(cwd=None):
    d = json.loads(client.run(["repo", "view", "--json", "owner,name"], cwd=cwd))
    return d["owner"]["login"], d["name"]


def set_variable(cfg, name, value):
    client.run(["variable", "set", name, "-R", client.repo_full(cfg), "--body", value])


def ensure_issue_types(org, names):
    try:
        existing = {t["name"] for t in client.rest("GET", f"orgs/{org}/issue-types")}
    except client.GhError as e:
        raise client.GhError(f"Không đọc được Issue Types của '{org}'. omi-hub cần repo thuộc Organization "
                      f"và token có admin:org. Chi tiết: {e}") from None
    for name in names:
        if name not in existing:
            client.rest("POST", f"orgs/{org}/issue-types", {"name": name, "is_enabled": True})


def find_project(owner, title):
    d = json.loads(client.run(["project", "list", "--owner", owner, "--format", "json", "--limit", "200"]))
    return next((p["number"] for p in d["projects"] if p["title"] == title), None)


def create_project(owner, title):
    return json.loads(client.run(["project", "create", "--owner", owner, "--title", title, "--format", "json"]))["number"]


def copy_project(owner, source, title):
    return json.loads(client.run(["project", "copy", str(source), "--source-owner", owner, "--target-owner", owner,
                           "--title", title, "--format", "json"]))["number"]


def project_node_id(owner, number):
    return json.loads(client.run(["project", "view", str(number), "--owner", owner, "--format", "json"]))["id"]


def default_branch(owner, repo):
    return client.run(["repo", "view", f"{owner}/{repo}", "--json", "defaultBranchRef",
                "-q", ".defaultBranchRef.name"]).strip()


def ensure_label(cfg, name):
    client.run(["label", "create", name, "-R", client.repo_full(cfg), "--force", "--color", "B60205",
         "--description", "Chạm security: bật security review"])


def link_project(owner, number, repo_full):
    client.run(["project", "link", str(number), "--owner", owner, "--repo", repo_full])


def _field_list(owner, number):
    return json.loads(client.run(["project", "field-list", str(number), "--owner", owner,
                           "--format", "json", "--limit", "100"]))["fields"]


def ensure_fields(owner, number, wf):
    fields = {f["name"]: f for f in _field_list(owner, number)}
    status = fields["Status"]
    if [o["name"] for o in status.get("options", [])] != wf["statuses"]:
        items = json.loads(client.run(["project", "item-list", str(number), "--owner", owner,
                                "--format", "json", "--limit", "1"]))["items"]
        if items:
            raise client.GhError(f"Status của Project #{number} khác chuẩn omi và đã có item. "
                          f"Sửa tay options Status thành: {', '.join(wf['statuses'])}")
        client.graphql(UPDATE_STATUS, field=status["id"],
                options=[{"name": s, "color": STATUS_COLORS[s], "description": ""} for s in wf["statuses"]])
    wanted = {"Priority": ("SINGLE_SELECT", ",".join(wf["priorities"])), "Estimate": ("NUMBER", None),
              "Rework Count": ("NUMBER", None), "Blocked Reason": ("TEXT", None)}
    for name, (dtype, opts) in wanted.items():
        if name not in fields:
            args = ["project", "field-create", str(number), "--owner", owner, "--name", name, "--data-type", dtype]
            if opts:
                args += ["--single-select-options", opts]
            client.run(args)


def load_fields(owner, number):
    out = {}
    for f in _field_list(owner, number):
        if f["name"] in project.FIELD_KINDS:
            out[f["name"]] = {"id": f["id"]}
            if f.get("options"):
                out[f["name"]]["options"] = {o["name"]: o["id"] for o in f["options"]}
    return out
