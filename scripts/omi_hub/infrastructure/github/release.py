"""Luồng release: CODEOWNERS, nhánh develop, default branch, ruleset nhánh chính, PR release."""
import base64
import json

from . import client

RULESET = "omi-release"


def ensure_codeowners(cfg, branch, po):
    """Ghi `.github/CODEOWNERS` = `* @po` thẳng lên nhánh chính (GitHub đọc CODEOWNERS từ nhánh base)."""
    path, want = f"{client.repo_path(cfg)}/contents/.github/CODEOWNERS", f"* @{po}\n"
    body = {"message": f"chore: CODEOWNERS release cho @{po} (omi)", "branch": branch,
            "content": base64.b64encode(want.encode()).decode()}
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


def compare_commits(cfg, base, head):
    d = client.rest("GET", f"{client.repo_path(cfg)}/compare/{base}...{head}")
    return [c["commit"]["message"].splitlines()[0] for c in d["commits"]]


def pr_reviews(cfg, pr):
    out = client.run(["pr", "view", str(pr), "-R", client.repo_full(cfg), "--json", "reviews"])
    return [{"author": r["author"]["login"], "state": r["state"]} for r in json.loads(out)["reviews"]]
