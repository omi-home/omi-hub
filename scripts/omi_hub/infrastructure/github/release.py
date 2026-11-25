"""Luồng release: CODEOWNERS, nhánh develop, default branch, ruleset nhánh chính, PR release."""
import base64
import json

from . import client

RULESET = "omi-release"


def ensure_codeowners(cfg, branch, team):
    """Ghi `.github/CODEOWNERS` = `* @org/team` (GitHub đọc CODEOWNERS từ nhánh base).
    branch=None: repo rỗng, commit đầu lên nhánh mặc định của org."""
    path, want = f"{client.repo_path(cfg)}/contents/.github/CODEOWNERS", f"* @{team}\n"
    body = {"message": f"chore: CODEOWNERS release cho @{team} (omi)", "branch": branch,
            "content": base64.b64encode(want.encode()).decode()}
    if branch is None:
        del body["branch"]
        client.rest("PUT", path, body)
        return
    try:
        cur = client.rest("GET", f"{path}?ref={branch}")
    except client.GhError:
        cur = None  # chưa có file
    if cur:
        if base64.b64decode(cur["content"]).decode() == want:
            return
        body["sha"] = cur["sha"]
    client.rest("PUT", path, body)


def branch_exists(cfg, name):
    try:
        client.rest("GET", f"{client.repo_path(cfg)}/branches/{name}")
        return True
    except client.GhError:
        return False


def ensure_branch(cfg, name, from_branch):
    rp = client.repo_path(cfg)
    if branch_exists(cfg, name):
        return
    sha = client.rest("GET", f"{rp}/git/ref/heads/{from_branch}")["object"]["sha"]
    client.rest("POST", f"{rp}/git/refs", {"ref": f"refs/heads/{name}", "sha": sha})


def set_default_branch(cfg, name):
    client.rest("PATCH", client.repo_path(cfg), {"default_branch": name, "allow_merge_commit": True,
                                                 "allow_auto_merge": True})


def ensure_ruleset(cfg, branch):
    """None khi đã có/tạo được; chuỗi lỗi khi không tạo được (vd. repo private gói Free không có ruleset)."""
    rp = client.repo_path(cfg)
    try:
        if any(r["name"] == RULESET for r in client.rest("GET", f"{rp}/rulesets") or []):
            return None
        client.rest("POST", f"{rp}/rulesets", {
            "name": RULESET, "target": "branch", "enforcement": "active",
            "conditions": {"ref_name": {"include": [f"refs/heads/{branch}"], "exclude": []}},
            "rules": [{"type": "deletion"}, {"type": "non_fast_forward"},
                      {"type": "pull_request", "parameters": {
                          "required_approving_review_count": 1, "require_code_owner_review": True,
                          "dismiss_stale_reviews_on_push": True, "require_last_push_approval": False,
                          "required_review_thread_resolution": False, "allowed_merge_methods": ["merge"]}}]})
        return None
    except client.GhError as e:
        return str(e).splitlines()[0]


def _logins(path):
    """Login qua mọi trang (org/team có thể hơn 100 người)."""
    sep = "&" if "?" in path else "?"
    return client.run(["api", "--paginate", f"{path}{sep}per_page=100", "--jq", ".[].login"]).split()


def org_owners(org):
    return _logins(f"orgs/{org}/members?role=admin")


def ensure_team(cfg, slug):
    """Team tồn tại và có quyền push repo (CODEOWNERS chỉ nhận team có quyền ghi)."""
    org = cfg["owner"]
    try:
        client.rest("GET", f"orgs/{org}/teams/{slug}")
    except client.GhError:
        client.rest("POST", f"orgs/{org}/teams", {"name": slug, "privacy": "closed",
                                                  "description": "PO: owner của org, duyệt release (omi)"})
    client.rest("PUT", f"orgs/{org}/teams/{slug}/repos/{cfg['owner']}/{cfg['repo']}", {"permission": "push"})


def team_members(cfg, slug):
    return _logins(f"orgs/{cfg['owner']}/teams/{slug}/members")


def add_team_member(cfg, slug, login):
    client.rest("PUT", f"orgs/{cfg['owner']}/teams/{slug}/memberships/{login}", {"role": "member"})


def remove_team_member(cfg, slug, login):
    client.rest("DELETE", f"orgs/{cfg['owner']}/teams/{slug}/memberships/{login}")


def compare_commits(cfg, base, head):
    d = client.rest("GET", f"{client.repo_path(cfg)}/compare/{base}...{head}")
    return [c["commit"]["message"].splitlines()[0] for c in d["commits"]]


def pr_reviews(cfg, pr):
    out = client.run(["pr", "view", str(pr), "-R", client.repo_full(cfg), "--json", "reviews"])
    return [{"author": r["author"]["login"], "state": r["state"]} for r in json.loads(out)["reviews"]]


def has_ruleset(cfg):
    return any(r["name"] == RULESET for r in client.rest("GET", f"{client.repo_path(cfg)}/rulesets") or [])
