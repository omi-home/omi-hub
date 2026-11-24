"""Branch phát triển của issue và Pull Request."""
import json
import re

from . import client


def issue_branches(cfg, n):
    out = client.run(["issue", "develop", "--list", str(n), "-R", client.repo_full(cfg)])
    return [line.split()[0] for line in out.splitlines() if line.strip()]


def develop(cfg, n, cwd=None):
    client.run(["issue", "develop", str(n), "-R", client.repo_full(cfg), "--checkout"], cwd=cwd)


def create_pr(cfg, title, body, head):
    url = client.run(["pr", "create", "-R", client.repo_full(cfg), "--head", head, "--title", title,
               "--body-file", "-"], input=body).strip().splitlines()[-1]
    return int(url.rstrip("/").split("/")[-1])


def open_pr_for_branch(cfg, head):
    """PR đang mở từ branch: không phụ thuộc liên kết issue (GitHub cập nhật trễ)."""
    out = client.run(["pr", "list", "-R", client.repo_full(cfg), "--head", head, "--state", "open", "--json", "number"])
    prs = json.loads(out or "[]")
    return prs[0]["number"] if prs else None


def pr_view(cfg, pr):
    d = json.loads(client.run(["pr", "view", str(pr), "-R", client.repo_full(cfg), "--json", "title,body"]))
    return d["title"], d["body"]


def pr_diff(cfg, pr):
    return client.run(["pr", "diff", str(pr), "-R", client.repo_full(cfg)])


def pr_checks(cfg, pr):
    """(True|False, output) khi PR có CI; (None, "") khi không có check nào."""
    try:
        return True, client.run(["pr", "checks", str(pr), "-R", client.repo_full(cfg), "--watch", "--fail-fast"])
    except client.GhError as e:
        if "no checks reported" in str(e).lower():
            return None, ""
        return False, str(e) + _failed_logs(cfg, str(e))


def _failed_logs(cfg, table, lines=60):
    """Nguyên nhân fail: tail `gh run view --log-failed` của từng run có check fail."""
    runs = dict.fromkeys(m.group(1) for row in table.splitlines() if "\tfail\t" in row
                         for m in [re.search(r"/actions/runs/(\d+)", row)] if m)
    out = []
    for run in runs:
        try:
            log = client.run(["run", "view", run, "-R", client.repo_full(cfg), "--log-failed"])
        except client.GhError as e:
            log = str(e)
        out.append(f"\n\n## Run {run} (log-failed)\n" + "\n".join(log.splitlines()[-lines:]))
    return "".join(out)


def merge_pr(cfg, pr):
    client.run(["pr", "merge", str(pr), "-R", client.repo_full(cfg), "--squash", "--delete-branch"])
