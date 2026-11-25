"""Khởi tạo: Issue Types, Project, fields, label, variable."""
import base64
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


VIEWS_QUERY = "query($p: ID!) { node(id: $p) { ... on ProjectV2 { views(first: 50) { nodes { name } } } } }"
CREATE_VIEW = """mutation($p: ID!, $name: String!, $layout: ProjectV2ViewLayout!) {
  createProjectV2View(input: {projectId: $p, name: $name, layout: $layout}) { projectV2View { id } } }"""
FILTER_VIEW = """mutation($v: ID!, $filter: String!) {
  updateProjectV2View(input: {viewId: $v, filter: $filter}) { projectV2View { id } } }"""


def ensure_views(project_id, views):
    """Tạo view còn thiếu theo tên (layout + filter); group by/sort API chưa hỗ trợ. Trả tên view vừa tạo."""
    have = {v["name"] for v in client.graphql(VIEWS_QUERY, p=project_id)["node"]["views"]["nodes"]}
    made = []
    for v in views:
        if v["name"] in have:
            continue
        vid = client.graphql(CREATE_VIEW, p=project_id, name=v["name"],
                             layout=v["layout"])["createProjectV2View"]["projectV2View"]["id"]
        if v.get("filter"):
            client.graphql(FILTER_VIEW, v=vid, filter=v["filter"])
        made.append(v["name"])
    return made


def remote_json(repo_full, path):
    """Đọc file JSON trên nhánh mặc định của repo khác (vd. plugin.json của hub)."""
    return json.loads(base64.b64decode(client.rest("GET", f"repos/{repo_full}/contents/{path}")["content"]))


def get_variable(cfg, name):
    return client.run(["variable", "get", name, "-R", client.repo_full(cfg)]).strip()


def secret_names(cfg):
    return {s["name"] for s in json.loads(client.run(["secret", "list", "-R", client.repo_full(cfg), "--json", "name"]))}
