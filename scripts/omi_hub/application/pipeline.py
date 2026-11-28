"""Use case pipeline một task: context → start → check → submit → qa → accept; impact, plan-show, pr-lint."""
import json
import re
import time
from pathlib import Path

from omi_hub.application import handoff, items
from omi_hub.application.workspace import repo_dir, tmp_dir
from omi_hub.config import load_pr_template, load_templates
from omi_hub.domain.acceptance import accept_verdict, parse_ac
from omi_hub.domain.docs import doc_refs, render_refs, section
from omi_hub.domain import findings
from omi_hub.domain.errors import RuleError
from omi_hub.domain.planning import AC_TYPES, pick_next, validate_plan
from omi_hub.domain.progress import resume_step
from omi_hub.domain.rework import DEFAULT_CI_INFRA, infra_reason
from omi_hub.domain.render import filter_diff, pr_title, render_context, render_plan, render_pr_body, tail
from omi_hub.domain.security import DEFAULT_SECURITY, needs_security
from omi_hub.domain.templates import check_pr, sections
from omi_hub.domain.text import affected, find_marker
from omi_hub.infrastructure.github import gateway as gh
from omi_hub.infrastructure.shell import run_cmd


CHECK_STEPS = ("lint", "typecheck", "scan", "test")
TMP_MAX_AGE = 7 * 86400  # giây; file .omi/tmp cũ hơn bị dọn khi start
LINK_WAIT = (1, 2, 4, 8)  # giây chờ GitHub liên kết PR mới vào issue (closedByPullRequestsReferences)
CLOSING = re.compile(r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)", re.I)  # từ khoá đóng issue của GitHub


def _open_pr(snap):
    return next((p["number"] for p in snap["prs"] if p["state"] == "OPEN"), None)


def _wait_linked(cfg, n):
    for delay in (0, *LINK_WAIT):
        time.sleep(delay)
        if _open_pr(gh.issue_snapshot(cfg, n)):
            return
    raise RuleError(f"GitHub chưa liên kết PR vào #{n} sau {sum(LINK_WAIT)}s — chạy lại `submit {n}` (không tạo PR trùng)")


def doc_context(cfg, bodies):
    """Ghép các mục docs được tham chiếu trong `### Tham chiếu` của task/parent; tham chiếu hỏng → cảnh báo."""
    root = Path(repo_dir(cfg)).resolve()
    refs = []
    for b in bodies:
        refs += [r for r in doc_refs(b) if r not in refs]
    found, missing = [], []
    for path, anchor in refs:
        label = path + (f"#{anchor}" if anchor else "")
        f = (root / path).resolve()
        text = None
        if f.is_relative_to(root) and f.is_file():  # không đọc file ngoài repo
            md = f.read_text(encoding="utf-8")
            text = section(md, anchor) if anchor else md.strip()
        (found.append((label, text)) if text else missing.append(label))
    return render_refs(found, missing)


def context(cfg, n):
    s = gh.issue_snapshot(cfg, n)
    parent = gh.issue_snapshot(cfg, s["parent"]["number"]) if s["parent"] else None
    text = render_context(s, parent, [gh.issue_snapshot(cfg, a) for a in affected(s["body"])])
    docs = doc_context(cfg, [s["body"]] + ([parent["body"]] if parent else []))
    text += f"\n\n{docs}" if docs else ""
    carried = carried_findings(cfg, parent)
    text += f"\n\n## Findings mang theo\n{carried}" if carried else ""
    print(text)
    return text


def _ancestor_findings(cfg, anc):
    """{p: (comment_id, items)} của parent và mọi tổ tiên."""
    out = {}
    while anc:
        cid, body = gh.marked_comment(cfg, anc["number"], findings.NAME)
        out[anc["number"]] = (cid, findings.parse(body))
        anc = gh.issue_snapshot(cfg, anc["parent"]["number"]) if anc["parent"] else None
    return out


def carried_findings(cfg, anc):
    """Finding còn mở của parent và mọi tổ tiên, mỗi dòng có mã `<p>.<i>`."""
    return "\n".join(f"- [{code}] {t}" for p, (_, its) in _ancestor_findings(cfg, anc).items()
                     for code, t in findings.open_codes(p, its))


def done_findings(cfg, s, raw):
    """`submit --findings`: kiểm hết mã trước (sai → lỗi, không sửa gì) rồi đánh dấu `[x] ... (xong ở #n)`."""
    want = findings.parse_codes(raw)
    have = _ancestor_findings(cfg, gh.issue_snapshot(cfg, s["parent"]["number"]) if s["parent"] else None)
    bad = [f"{p}.{i}" for p, idx in want.items() for i in sorted(idx)
           if p not in have or f"{p}.{i}" not in dict(findings.open_codes(p, have[p][1]))]
    if bad:
        raise RuleError(f"Mã finding không tồn tại/không còn mở cho #{s['number']}: {', '.join(bad)}"
                        " — xem `context`")
    for p, idx in want.items():
        cid, its = have[p]
        gh.upsert_comment(cfg, p, cid, findings.render(findings.mark(its, idx, f"xong ở #{s['number']}")))
    if want:
        print(f"FINDINGS xong: {raw}")


def start(cfg, wf, n=None):
    if n is None:
        it = pick_next(wf, gh.project_items(cfg))
        if not it:
            print("NONE")
            return None
        n = it["number"]
    status = items.snapshot(cfg, n)["status"]
    if status == "Draft":
        status = items.move(cfg, wf, n, "Ready")  # còn blocker mở → Waiting, không start
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
    pruned = prune_tmp(cfg, n)
    if pruned:
        print(f"Đã dọn {pruned} file cũ trong .omi/tmp")
    print(f"START #{n}")
    return n


def prune_tmp(cfg, n, now=None):
    """Xoá file .omi/tmp cũ hơn TMP_MAX_AGE, trừ `current` và file của task n."""
    keep = {"current", *items.task_files(n)}
    limit = (now or time.time()) - TMP_MAX_AGE
    old = [f for f in tmp_dir(cfg).iterdir() if f.is_file() and f.name not in keep and f.stat().st_mtime < limit]
    for f in old:
        f.unlink()
    return len(old)


def check(cfg):
    for step in CHECK_STEPS:
        cmd = cfg.get("commands", {}).get(step)
        if cmd:
            code, out = run_cmd(cmd, cwd=repo_dir(cfg))
            if code:
                msg = f"CHECK FAIL ({step})\n{tail(out)}"
                _save_check(cfg, msg)
                print(msg)
                return 1
    msg = "CHECK PASS" if cfg.get("commands", {}).get("test") else "CHECK WARN: chưa cấu hình commands.test"
    _save_check(cfg, msg)
    print(msg)
    return 0


def _save_check(cfg, msg):
    """Kết quả `check` gần nhất cho gói review."""
    tmp_dir(cfg).mkdir(parents=True, exist_ok=True)
    (tmp_dir(cfg) / "check-last.txt").write_text(msg, encoding="utf-8")


def task_branch(cfg, n):
    """(nhánh hiện tại, có phải nhánh của task n): tên `n-...` (gh issue develop) hoặc nhánh liên kết với issue."""
    _, head = run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_dir(cfg))
    head = head.strip()
    return head, bool(re.search(rf"(?:^|/){n}(?:-|$)", head)) or head in gh.issue_branches(cfg, n)


def _check_branch(cfg, n, base):
    """submit chỉ từ nhánh của n, và commit không đóng issue khác (squash merge giữ body commit)."""
    head, ok = task_branch(cfg, n)
    if not ok:
        raise RuleError(f"Nhánh hiện tại '{head}' không phải nhánh của #{n} — `start {n}` để checkout đúng nhánh")
    run_cmd(["git", "fetch", "origin", base.removeprefix("origin/")], cwd=repo_dir(cfg))  # base cũ → lẫn commit đã merge
    _, msgs = run_cmd(["git", "log", "--format=%B", f"{base}..HEAD"], cwd=repo_dir(cfg))
    other = sorted({int(m) for m in CLOSING.findall(msgs)} - {n})
    if other:
        raise RuleError(f"Commit trên nhánh đóng issue khác: {', '.join(f'#{x}' for x in other)}"
                        f" — sửa message commit (chỉ `Closes #{n}`)")
    return head


def submit(cfg, wf, n, done=None):
    s = items.snapshot(cfg, n)
    if s["status"] not in ("In Progress", "In Review"):
        raise RuleError(f"#{n} phải ở In Progress/In Review (hiện: {s['status']})")
    base = f"origin/{cfg.get('default_branch', 'main')}"
    head = _check_branch(cfg, n, base)
    if done:
        done_findings(cfg, s, done)
    code, out = run_cmd(["git", "push", "-u", "origin", "HEAD"], cwd=repo_dir(cfg))
    if code:
        raise RuleError("git push lỗi:\n" + tail(out, 20))
    parent = gh.issue_snapshot(cfg, s["parent"]["number"]) if s["parent"] else None
    _, files = run_cmd(["git", "diff", "--name-only", f"{base}...HEAD"], cwd=repo_dir(cfg))
    sec = needs_security(files.split(), s["labels"] + (parent["labels"] if parent else []), parent,
                         cfg.get("security_paths", DEFAULT_SECURITY))
    pr = _open_pr(s)
    if pr is None:
        pr = gh.open_pr_for_branch(cfg, head)  # PR đã tạo nhưng issue chưa kịp liên kết → không tạo trùng
    _, log = run_cmd(["git", "log", "--format=%s", f"{base}..HEAD"], cwd=repo_dir(cfg))
    if pr is None:  # title + body PR theo pr_template.json, do script sinh
        pr = gh.create_pr(cfg, pr_title(s), render_pr_body(s, parent, log.splitlines(), sec), head)
    if s["status"] == "In Progress":
        _wait_linked(cfg, n)  # guard In Review cần PR đã liên kết
        items.move(cfg, wf, n, "In Review")
    reviewers = []
    if find_marker(gh.comments(cfg, n), "reviewed") is None:  # review LLM chỉ 1 lượt mỗi task
        reviewers = ["code"] + (["security"] if sec else [])
        diff, dropped = filter_diff(gh.pr_diff(cfg, pr).splitlines())
        limit = cfg.get("review_max_diff_lines", 1500)
        tmp_dir(cfg).mkdir(parents=True, exist_ok=True)
        pack = tmp_dir(cfg) / f"review-{n}.md"
        last = tmp_dir(cfg) / "check-last.txt"
        sibs = [f"- #{c['number']} {c.get('title') or ''} — {c['status']}" for c in (parent or {}).get("children", [])
                if c["number"] != n and c["state"] == "OPEN"]
        known = carried_findings(cfg, parent)
        parts = [render_context(s, parent, [gh.issue_snapshot(cfg, a) for a in affected(s["body"])]),
                 "## Commit\n" + ("\n".join(f"- {x}" for x in log.splitlines() if x.strip()) or "(không có)"),
                 "## Check gần nhất\n" + (last.read_text(encoding="utf-8") if last.exists() else "(chưa chạy `check`)"),
                 "## Task anh em còn mở\n" + ("\n".join(sibs) or "(không có)"),
                 "## Findings đã có (không báo lại)\n" + (known or "(không có)"),
                 f"## Diff PR #{pr} ({len(diff)} dòng)"
                 + (f"\nĐã bỏ file sinh/lockfile: {', '.join(dropped)}" if dropped else "")
                 + "\n```diff\n" + "\n".join(diff[:limit])
                 + ("\n... (đã cắt)" if len(diff) > limit else "") + "\n```"]
        pack.write_text("\n\n".join(parts) + "\n", encoding="utf-8")
        print(f"REVIEW #{n} PR #{pr} pack={pack.as_posix()} reviewers={','.join(reviewers)}")
    else:
        print(f"REVIEW #{n} PR #{pr} reviewers=none")
    return pr, reviewers


def qa(cfg, wf, n):
    s = items.snapshot(cfg, n)
    if s["status"] not in ("In Review", "In QA"):
        raise RuleError(f"#{n} phải ở In Review/In QA (hiện: {s['status']})")
    pr = _open_pr(s)
    if pr is None:
        raise RuleError(f"#{n} không có PR mở")
    ok, out = gh.pr_checks(cfg, pr)
    infra = None if ok is not False else infra_reason(out, cfg.get("ci_infra_patterns", DEFAULT_CI_INFRA))
    if infra:  # lỗi hạ tầng CI: không rework, giữ nguyên status
        print(f"QA INFRA {infra}")
        return 1
    if s["status"] == "In Review":
        items.move(cfg, wf, n, "In QA")
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
    auto_handoff(cfg, wf)
    return 0


def auto_handoff(cfg, wf):
    """Sau DONE/Cancelled: cập nhật HANDOFF bằng script; lỗi chỉ cảnh báo, không làm hỏng lệnh chính."""
    try:
        handoff.handoff(cfg, wf)
    except Exception as e:  # noqa: BLE001 — handoff là phụ, không được làm fail qa/move
        print(f"HANDOFF WARN: {str(e).splitlines()[0] if str(e) else type(e).__name__}")


def sync_main(cfg):
    """Nghiệm thu chạy trên nhánh chính mới nhất (đã có PR vừa merge), không phải nhánh task/bản local cũ."""
    b = cfg.get("default_branch", "main")
    for cmd in (["git", "fetch", "origin", b], ["git", "checkout", b], ["git", "merge", "--ff-only", f"origin/{b}"]):
        code, out = run_cmd(cmd, cwd=repo_dir(cfg))
        if code:
            raise RuleError(f"Không cập nhật được nhánh {b} để nghiệm thu (`{' '.join(cmd)}`):\n{tail(out, 10)}")


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
        sync_main(cfg)
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
    head, on_branch = task_branch(cfg, n) if s["status"] == "In Progress" else ("", True)
    step, hint = resume_step(s["status"], bool(dirty.strip()), int(ahead.strip()) if ahead.strip().isdigit() else 0,
                             reviewed, (tmp_dir(cfg) / f"review-{n}.md").exists(), on_branch)
    if step == "next":
        cur.unlink(missing_ok=True)
        handoff.clear_wip(cfg)
    print(f"RESUME #{n} status={s['status']} step={step}" + (f" branch={head}" if not on_branch else "")
          + f"\n{hint.replace('<n>', str(n))}")
    wip = handoff.wip_text(cfg) if step != "next" else None
    if wip:
        print(f"\n## Checkpoint phiên trước\n{wip}")
    if step in ("code", "submit"):
        print()
        context(cfg, n)
    return step


def add_findings(cfg, n, texts):
    """IMPROVE của review #n → comment findings của parent (không tạo issue mới)."""
    s = gh.issue_snapshot(cfg, n)
    if not s["parent"]:
        raise RuleError(f"#{n} không có parent để ghi findings")
    p = s["parent"]["number"]
    cid, body = gh.marked_comment(cfg, p, findings.NAME)
    its, added = findings.parse(body), 0
    for t in texts:
        its, ok = findings.add(its, t, f"từ #{n}")
        added += ok
    if added:
        gh.upsert_comment(cfg, p, cid, findings.render(its))
    print(f"FINDINGS #{p} +{added} (bỏ {len(texts) - added} trùng)")


def carry(cfg, wf, nums):
    """Task Draft cũ (gợi ý review kiểu trước) → finding của parent, Task → Cancelled."""
    for n in nums:
        s = items.snapshot(cfg, n)
        if s["type"] != "Task" or s["status"] != "Draft" or not s["parent"]:
            raise RuleError(f"#{n}: carry chỉ nhận Task Draft có parent (hiện: {s['type']} {s['status']})")
        title = s["title"].removeprefix("[Task] ").strip()
        todo = "; ".join(x.strip().lstrip("-*").strip() for x in
                         sections(s["body"]).get("Việc cần làm", "").splitlines() if x.strip())
        text = title if not todo or todo.casefold() == title.casefold() else f"{title}: {todo}"
        p = s["parent"]["number"]
        cid, body = gh.marked_comment(cfg, p, findings.NAME)
        its, ok = findings.add(findings.parse(body), text, f"từ #{n}")
        if ok:
            gh.upsert_comment(cfg, p, cid, findings.render(its))
        items.move(cfg, wf, n, "Cancelled", f"Gộp thành finding của #{p} (carry)")
        print(f"CARRY #{n} → finding #{p}{'' if ok else ' (đã có, bỏ trùng)'}")


def review_done(cfg, wf, n, fail=None, improve=(), override=None):
    """Ghi nhận review 1 lượt SAU khi reviewer trả kết quả (resume dựa vào marker này); FAIL → rework."""
    if fail and override:
        raise RuleError("--fail và --override loại trừ nhau")
    if override is not None and not override.strip():
        raise RuleError("--override cần lý do bác BLOCKER")
    if improve:
        add_findings(cfg, n, improve)
    if override:  # BLOCKER của reviewer sai: PASS kèm lý do, ghi cả issue lẫn PR để người xem lại được
        note = f"🔎 Review 1 lượt: PASS (bác BLOCKER) — {override}"
        gh.comment(cfg, n, f"<!-- omi:reviewed -->\n{note}")
        pr = _open_pr(gh.issue_snapshot(cfg, n))
        if pr:
            gh.comment(cfg, pr, note)
        print(f"REVIEWED #{n} PASS (override)")
        return
    gh.comment(cfg, n, f"<!-- omi:reviewed -->\n🔎 Review 1 lượt: {'FAIL — ' + fail if fail else 'PASS'}")
    if fail:
        items.rework(cfg, wf, n, f"Review: {fail}")
    print(f"REVIEWED #{n} {'FAIL' if fail else 'PASS'}")
