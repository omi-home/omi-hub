"""Use case pipeline một task: context → start → check → submit → qa → accept; impact, plan-show, pr-lint."""
import json
import time
from pathlib import Path

from omi_hub.application import items
from omi_hub.application.workspace import repo_dir, tmp_dir
from omi_hub.config import load_pr_template, load_templates
from omi_hub.domain.acceptance import accept_verdict, parse_ac
from omi_hub.domain.errors import RuleError
from omi_hub.domain.planning import AC_TYPES, pick_next, validate_plan
from omi_hub.domain.progress import resume_step
from omi_hub.domain.render import pr_title, render_context, render_plan, render_pr_body, tail
from omi_hub.domain.security import DEFAULT_SECURITY, needs_security
from omi_hub.domain.templates import check_pr
from omi_hub.domain.text import affected, find_marker
from omi_hub.infrastructure.github import gateway as gh
from omi_hub.infrastructure.shell import run_cmd


CHECK_STEPS = ("lint", "typecheck", "scan", "test")
LINK_WAIT = (1, 2, 4, 8)  # giây chờ GitHub liên kết PR mới vào issue (closedByPullRequestsReferences)


def _open_pr(snap):
    return next((p["number"] for p in snap["prs"] if p["state"] == "OPEN"), None)


def _wait_linked(cfg, n):
    for delay in (0, *LINK_WAIT):
        time.sleep(delay)
        if _open_pr(gh.issue_snapshot(cfg, n)):
            return
    raise RuleError(f"GitHub chưa liên kết PR vào #{n} sau {sum(LINK_WAIT)}s — chạy lại `submit {n}` (không tạo PR trùng)")


def context(cfg, n):
    s = gh.issue_snapshot(cfg, n)
    parent = gh.issue_snapshot(cfg, s["parent"]["number"]) if s["parent"] else None
    text = render_context(s, parent, [gh.issue_snapshot(cfg, a) for a in affected(s["body"])])
    print(text)
    return text


def start(cfg, wf, n=None):
    if n is None:
        it = pick_next(wf, gh.project_items(cfg))
        if not it:
            print("NONE")
            return None
        n = it["number"]
    status = items.snapshot(cfg, n)["status"]
    if status == "Draft":
        items.move(cfg, wf, n, "Ready")
        status = "Ready"
    if status == "Ready":
        items.move(cfg, wf, n, "In Progress")
    elif status != "In Progress":
        raise RuleError(f"#{n} đang ở '{status}', không start được")
    branches = gh.issue_branches(cfg, n)
    if branches:
        run_cmd(["git", "fetch", "origin"], cwd=repo_dir(cfg))
        code, out = run_cmd(["git", "checkout", branches[0]], cwd=repo_dir(cfg))
        if code:
            raise RuleError("git checkout lỗi:\n" + tail(out, 10))
    else:
        gh.develop(cfg, n, cwd=repo_dir(cfg))
    tmp_dir(cfg).mkdir(parents=True, exist_ok=True)
    (tmp_dir(cfg) / "current").write_text(str(n), encoding="utf-8")  # hook SessionStart nạp lại context sau /clear
    print(f"START #{n}")
    return n


def check(cfg):
    for step in CHECK_STEPS:
        cmd = cfg.get("commands", {}).get(step)
        if cmd:
            code, out = run_cmd(cmd, cwd=repo_dir(cfg))
            if code:
                print(f"CHECK FAIL ({step})\n{tail(out)}")
                return 1
    print("CHECK PASS")
    return 0


def submit(cfg, wf, n):
    s = items.snapshot(cfg, n)
    if s["status"] not in ("In Progress", "In Review"):
        raise RuleError(f"#{n} phải ở In Progress/In Review (hiện: {s['status']})")
    code, out = run_cmd(["git", "push", "-u", "origin", "HEAD"], cwd=repo_dir(cfg))
    if code:
        raise RuleError("git push lỗi:\n" + tail(out, 20))
    parent = gh.issue_snapshot(cfg, s["parent"]["number"]) if s["parent"] else None
    base = f"origin/{cfg.get('default_branch', 'main')}"
    _, files = run_cmd(["git", "diff", "--name-only", f"{base}...HEAD"], cwd=repo_dir(cfg))
    sec = needs_security(files.split(), s["labels"] + (parent["labels"] if parent else []), parent,
                         cfg.get("security_paths", DEFAULT_SECURITY))
    pr = _open_pr(s)
    if pr is None:
        _, head = run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_dir(cfg))
        pr = gh.open_pr_for_branch(cfg, head.strip())  # PR đã tạo nhưng issue chưa kịp liên kết → không tạo trùng
    if pr is None:  # title + body PR theo pr_template.json, do script sinh
        _, log = run_cmd(["git", "log", "--format=%s", f"{base}..HEAD"], cwd=repo_dir(cfg))
        pr = gh.create_pr(cfg, pr_title(s), render_pr_body(s, parent, log.splitlines(), sec), head.strip())
    if s["status"] == "In Progress":
        _wait_linked(cfg, n)  # guard In Review cần PR đã liên kết
        items.move(cfg, wf, n, "In Review")
    reviewers = []
    if find_marker(gh.comments(cfg, n), "reviewed") is None:  # review LLM chỉ 1 lượt mỗi task
        reviewers = ["code"] + (["security"] if sec else [])
        diff = gh.pr_diff(cfg, pr).splitlines()
        limit = cfg.get("review_max_diff_lines", 1500)
        tmp_dir(cfg).mkdir(parents=True, exist_ok=True)
        pack = tmp_dir(cfg) / f"review-{n}.md"
        pack.write_text(
            render_context(s, parent, [gh.issue_snapshot(cfg, a) for a in affected(s["body"])])
            + f"\n\n## Diff PR #{pr} ({len(diff)} dòng)\n```diff\n" + "\n".join(diff[:limit])
            + ("\n... (đã cắt)" if len(diff) > limit else "") + "\n```\n", encoding="utf-8")
        print(f"REVIEW #{n} PR #{pr} pack={pack.as_posix()} reviewers={','.join(reviewers)}")
    else:
        print(f"REVIEW #{n} PR #{pr} reviewers=none")
    return pr, reviewers


def qa(cfg, wf, n):
    s = items.snapshot(cfg, n)
    if s["status"] == "In Review":
        items.move(cfg, wf, n, "In QA")
    elif s["status"] != "In QA":
        raise RuleError(f"#{n} phải ở In Review/In QA (hiện: {s['status']})")
    pr = _open_pr(s)
    if pr is None:
        raise RuleError(f"#{n} không có PR mở")
    ok, out = gh.pr_checks(cfg, pr)
    why = "CI"
    if ok is None:  # không có CI: chạy test cục bộ; có CI thì không chạy trùng
        test = cfg.get("commands", {}).get("test")
        if not test:
            raise RuleError("PR không có CI và chưa cấu hình commands.test trong .omi/project.json")
        code, out = run_cmd(test, cwd=repo_dir(cfg))
        ok, why = code == 0, "test"
    if not ok:
        tmp_dir(cfg).mkdir(parents=True, exist_ok=True)
        log = tmp_dir(cfg) / f"qa-{n}.log"
        log.write_text(tail(out, 200), encoding="utf-8")
        status = items.rework(cfg, wf, n, f"QA fail ({why}), log: {log.as_posix()}")
        print(f"QA FAIL #{n} ({why}) log={log.as_posix()} status={status}")
        return 1
    gh.merge_pr(cfg, pr)
    items.move(cfg, wf, n, "Done")
    print(f"DONE #{n}")
    (tmp_dir(cfg) / "current").unlink(missing_ok=True)
    if s["parent"]:
        p = items.snapshot(cfg, s["parent"]["number"])
        if p["status"] == "In QA" and p["type"] in AC_TYPES:
            accept(cfg, wf, p["number"])
    return 0


def accept(cfg, wf, n):
    s = items.snapshot(cfg, n)
    if s["status"] != "In QA":
        raise RuleError(f"#{n} phải ở In QA (hiện: {s['status']})")
    acs = parse_ac(s["body"])
    if not acs:
        raise RuleError(f"#{n} không có mục '### Acceptance criteria'")
    code, out = 0, ""
    if any(not a["manual"] for a in acs):
        cmd = cfg.get("commands", {}).get("accept")
        if not cmd:
            raise RuleError("Chưa cấu hình commands.accept trong .omi/project.json")
        code, out = run_cmd(cmd.format(n=n), cwd=repo_dir(cfg))
    ok, missing = accept_verdict(n, acs, out, code)
    if ok:
        items.move(cfg, wf, n, "Done")
        print(f"ACCEPT PASS #{n}")
        return 0
    print(f"ACCEPT FAIL #{n}: " + "; ".join(missing))
    if any("[manual]" not in m for m in missing):
        items.rework(cfg, wf, n, "Nghiệm thu fail: " + "; ".join(missing))
    return 1


def impact(cfg, n, post=False):
    s = items.snapshot(cfg, n)
    lines = ["<!-- omi:impact -->", f"## Ảnh hưởng của Change Request #{n}"]
    for a in affected(s["body"]):
        x = gh.issue_snapshot(cfg, a)
        lines.append(f"- #{a} {x['title']} — {x['status']}")
        lines += [f"  - #{c['number']} {c['title']} — {c['status']}" for c in x["children"]]
    text = "\n".join(lines)
    print(text)
    if post:
        gh.comment(cfg, n, text)
    return text


def plan_show(wf, path):
    plan = json.loads(Path(path).read_text(encoding="utf-8"))
    errs = validate_plan(wf, plan, load_templates())
    if errs:
        raise RuleError(errs)
    print(render_plan(plan))
    return 0


def pr_lint(cfg, pr):
    title, body, head = gh.pr_view(cfg, pr)
    if cfg.get("main_branch") and head == cfg.get("default_branch"):  # PR release develop→main: không theo mẫu task
        print("PR OK (release)")
        return 0
    errs = check_pr(load_pr_template(), title, body)
    print("PR OK" if not errs else "PR FAIL\n" + "\n".join(f"- {e}" for e in errs))
    return 1 if errs else 0


def resume(cfg, wf):
    """Bước tiếp theo của task dở trong `.omi/tmp/current` (phiên trước dừng giữa chừng)."""
    cur = tmp_dir(cfg) / "current"
    if not cur.exists():
        print("RESUME none step=next — không có task dở; `start` để lấy task tiếp.")
        return None
    n = int(cur.read_text(encoding="utf-8").strip())
    s = gh.issue_snapshot(cfg, n)
    rd, base = repo_dir(cfg), f"origin/{cfg.get('default_branch', 'main')}"
    _, dirty = run_cmd(["git", "status", "--porcelain"], cwd=rd)
    _, ahead = run_cmd(["git", "rev-list", "--count", f"{base}..HEAD"], cwd=rd)
    reviewed = find_marker(gh.comments(cfg, n), "reviewed") is not None
    step, hint = resume_step(s["status"], bool(dirty.strip()), int(ahead.strip()) if ahead.strip().isdigit() else 0,
                             reviewed, (tmp_dir(cfg) / f"review-{n}.md").exists())
    if step == "next":
        cur.unlink(missing_ok=True)
    print(f"RESUME #{n} status={s['status']} step={step}\n{hint.replace('<n>', str(n))}")
    if step in ("code", "submit"):
        print()
        context(cfg, n)
    return step


def review_done(cfg, wf, n, fail=None):
    """Ghi nhận review 1 lượt SAU khi reviewer trả kết quả (resume dựa vào marker này); FAIL → rework."""
    gh.comment(cfg, n, f"<!-- omi:reviewed -->\n🔎 Review 1 lượt: {'FAIL — ' + fail if fail else 'PASS'}")
    if fail:
        items.rework(cfg, wf, n, f"Review: {fail}")
    print(f"REVIEWED #{n} {'FAIL' if fail else 'PASS'}")
