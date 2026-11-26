"""Use case vòng đời work item: new, move, rework, block, unblock + rollup lên parent."""
from omi_hub.application.workspace import tmp_dir
from omi_hub.config import load_templates
from omi_hub.domain import findings
from omi_hub.domain.errors import RuleError
from omi_hub.domain.guards import evaluate_guards
from omi_hub.domain.lifecycle import BLOCKED, WAITING, allowed_statuses, check_creatable, is_terminal, transition
from omi_hub.domain.relations import check_links, check_parent, rollup
from omi_hub.domain.rework import rework as rework_status
from omi_hub.domain.templates import check_template, replace_section, with_prefix
from omi_hub.domain.text import affected, build_body, find_marker
from omi_hub.infrastructure.github import gateway as gh


def snapshot(cfg, n):
    s = gh.issue_snapshot(cfg, n)
    if not s["item_id"]:
        raise RuleError(f"#{n} chưa có trong Project — chạy `audit --fix`")
    return s


def apply_status(cfg, wf, snap, target, reason=None):
    n = snap["number"]
    if target == BLOCKED:
        gh.comment(cfg, n, f"<!-- omi:blocked-from={snap['status']} -->\n🚧 Blocked: {reason or 'xem blocked-by'}")
        if reason:
            gh.set_field(cfg, snap["item_id"], "Blocked Reason", reason)
    elif snap["status"] == BLOCKED:
        gh.clear_field(cfg, snap["item_id"], "Blocked Reason")
        gh.comment(cfg, n, f"✅ Unblocked → {target}")
    elif reason:
        gh.comment(cfg, n, f"**{snap['status']} → {target}**: {reason}")
    gh.set_field(cfg, snap["item_id"], "Status", target)
    if is_terminal(wf, target) and snap["state"] == "OPEN":
        gh.close(cfg, n, "completed" if target == "Done" else "not_planned")
        snap["state"] = "CLOSED"
    print(f"#{n} {snap['type']}: {snap['status']} → {target}")
    snap["status"] = target
    if target in ("In QA", "Done"):
        escalate_findings(cfg, wf, snap)
    if is_terminal(wf, target):
        after_terminal(cfg, wf, snap)


def escalate_findings(cfg, wf, snap):
    """Item sang In QA/Done còn finding mở → chuyển lên parent (ghi nguồn); gốc kết thúc → báo FINDINGS OPEN."""
    n = snap["number"]
    cid, body = gh.marked_comment(cfg, n, findings.NAME)
    its = findings.parse(body)
    open_ = [(i, t) for i, (done, t) in enumerate(its, 1) if not done]
    if not open_:
        return
    if not snap["parent"]:
        if is_terminal(wf, snap["status"]):
            print(f"FINDINGS OPEN #{n} {len(open_)}")
        return
    p = snap["parent"]["number"]
    pcid, pbody = gh.marked_comment(cfg, p, findings.NAME)
    pits = findings.parse(pbody)
    for _, t in open_:
        pits, _ = findings.add(pits, t, f"chuyển từ #{n}")
    gh.upsert_comment(cfg, p, pcid, findings.render(pits))
    gh.upsert_comment(cfg, n, cid, findings.render(findings.mark(its, {i for i, _ in open_}, f"chuyển lên #{p}")))
    print(f"FINDINGS #{n} → #{p}: {len(open_)}")


def task_files(n):
    """File tạm của task n trong .omi/tmp."""
    return (f"review-{n}.md", f"qa-{n}.log")


def after_terminal(cfg, wf, snap):
    if cfg.get("_root"):  # Done/Cancelled: dọn file tạm của task; là task đang làm → bỏ current (checkpoint wip do handoff dọn)
        for f in task_files(snap["number"]):
            (tmp_dir(cfg) / f).unlink(missing_ok=True)
        cur = tmp_dir(cfg) / "current"
        if cur.exists() and cur.read_text(encoding="utf-8").strip() == str(snap["number"]):
            cur.unlink()
    release_dependents(cfg, wf, snap["number"])
    if snap.get("milestone") and gh.milestone_open_issues(cfg, snap["milestone"]) == 0:
        print(f"MILESTONE {snap['milestone']} sẵn sàng release")  # spec §4.6: báo, không tự đóng milestone


def release_dependents(cfg, wf, n):
    """n vừa kết thúc: issue Waiting mà hết blocker mở → Ready."""
    for d in gh.open_dependents(cfg, n):
        s = gh.issue_snapshot(cfg, d)
        if s["item_id"] and s["status"] == WAITING and s["open_blockers"] == 0:
            apply_status(cfg, wf, s, "Ready", f"Tự động: hết blocker (#{n} đã kết thúc)")


def rollup_up(cfg, wf, snap, trigger):
    if not snap["parent"]:
        return
    p = snapshot(cfg, snap["parent"]["number"])
    new = rollup(wf, p["type"], p["status"], [c["status"] for c in p["children"]], trigger)
    if not new:
        return
    apply_status(cfg, wf, p, new, f"Tự động (rollup từ #{snap['number']})")
    if p["type"] == "Change Request" and new == "Done":
        for a in affected(p["body"]):
            gh.comment(cfg, a, f"📝 Changelog: thay đổi theo Change Request #{p['number']} đã hoàn tất.")
    rollup_up(cfg, wf, p, new)


def _complete(cfg, n, parent, status, priority, estimate):
    s = gh.issue_snapshot(cfg, n)
    added = []
    if parent and not s["parent"]:
        gh.add_sub_issue(cfg, parent, gh.issue_db_id(cfg, n))
        added.append(f"parent #{parent}")
    item = s["item_id"]
    if not item:
        item = gh.add_to_project(cfg, s["id"])
        added.append("Project")
    if not s["status"]:
        gh.set_field(cfg, item, "Status", status)
        added.append(f"Status {status}")
        if priority:
            gh.set_field(cfg, item, "Priority", priority)
        if estimate is not None:
            gh.set_field(cfg, item, "Estimate", estimate)
    print(f"#{n} đã có (cùng type + title) → {'bổ sung ' + ', '.join(added) if added else 'đủ, không đổi'}; không tạo trùng")
    return n


def new_item(cfg, wf, type_, title, parent=None, affects=(), milestone=None, priority=None,
            estimate=None, body="", key=None, status=None, blocked_by=()):
    check_creatable(wf, type_)
    psnap = gh.issue_snapshot(cfg, parent) if parent else None
    check_parent(wf, type_, psnap["type"] if psnap else None)
    if milestone is None and psnap:
        milestone = psnap["milestone"]
    check_links(wf, type_, len(affects), bool(milestone))
    status = status or wf["types"][type_]["initial"]
    if status not in allowed_statuses(wf, type_):
        raise RuleError(f"{type_} không dùng status '{status}'")
    if priority and priority not in wf["priorities"]:
        raise RuleError(f"Priority phải là một trong {wf['priorities']}")
    tpl = load_templates()
    title = with_prefix(tpl, type_, title)  # prefix đầy đủ do script thêm, không cần người/LLM gõ
    full = build_body(body, affects, key)
    errs = check_template(tpl, type_, title, full)
    if errs:
        raise RuleError(errs + [f"Xem khung: `template \"{type_}\"`"])
    for a in affects:
        gh.issue_db_id(cfg, a)  # GhError nếu không tồn tại
    blocker_ids = [gh.issue_db_id(cfg, b) for b in blocked_by]  # kiểm tồn tại trước khi tạo
    old = gh.open_issue_by_title(cfg, title)
    if old:  # lần trước lỗi giữa chừng (hoặc gọi lại): bổ sung phần thiếu, không tạo trùng
        n = _complete(cfg, old, parent, status, priority, estimate)
        _link_blockers(cfg, n, blocked_by, blocker_ids)
        return n
    issue = gh.create_issue(cfg, title, full, type_, milestone)
    if psnap:
        gh.add_sub_issue(cfg, parent, issue["id"])
    item = gh.add_to_project(cfg, issue["node_id"])
    gh.set_field(cfg, item, "Status", status)
    if priority:
        gh.set_field(cfg, item, "Priority", priority)
    if estimate is not None:
        gh.set_field(cfg, item, "Estimate", estimate)
    print(f"#{issue['number']} {type_} '{title}' → {status}")
    _link_blockers(cfg, issue["number"], blocked_by, blocker_ids)
    return issue["number"]


def _link_blockers(cfg, n, nums, ids):
    """Quan hệ blocked-by; khi duyệt (`move Ready`) Task còn blocker mở tự vào Waiting."""
    have = set(gh.blocker_numbers(cfg, n)) if nums else set()
    for b, bid in zip(nums, ids):
        if b not in have:
            gh.add_blocked_by(cfg, n, bid)
            have.add(b)
    if nums:
        print(f"#{n} blocked-by " + ", ".join(f"#{b}" for b in nums))


def edit_item(cfg, n, fields, cr=None):
    """Thay mục body theo template; `cr` → comment changelog trỏ Change Request."""
    s = gh.issue_snapshot(cfg, n)
    if cr is not None and gh.issue_snapshot(cfg, cr)["type"] != "Change Request":
        raise RuleError(f"#{cr} không phải Change Request")
    tpl, body = load_templates(), s["body"]
    for h, v in fields.items():
        body = replace_section(tpl, s["type"], body, h, v)
    errs = check_template(tpl, s["type"], s["title"], body)
    if errs:
        raise RuleError(errs + [f"Xem khung: `template \"{s['type']}\"`"])
    gh.update_body(cfg, n, body)
    heads = ", ".join(f"`{h}`" for h in fields)
    if cr is not None:
        gh.comment(cfg, n, f"📝 Changelog: sửa mục {heads} theo Change Request #{cr}.")
    print(f"EDITED #{n} {heads}" + (f" (CR #{cr})" if cr is not None else ""))


def move(cfg, wf, n, target, reason=None):
    snap = snapshot(cfg, n)
    if snap["status"] == target:
        # Built-in workflow của Project (Item closed / PR merged) có thể đã set Done trước: chỉ chạy rollup.
        print(f"#{n} đã ở '{target}', chỉ chạy rollup")
        if is_terminal(wf, target):
            after_terminal(cfg, wf, snap)
        rollup_up(cfg, wf, snap, target)
        return target
    if (target == "Ready" and snap["open_blockers"] and snap["status"] != WAITING
            and WAITING in allowed_statuses(wf, snap["type"])):
        print(f"#{n} còn {snap['open_blockers']} blocker mở → {WAITING} thay vì Ready")
        target = WAITING
    blocked_from = (find_marker(gh.comments(cfg, n), "blocked-from")
                    if snap["status"] == BLOCKED else None)
    guards = transition(wf, snap["type"], snap["status"], target, blocked_from)
    if "impact_analysis" in guards:
        snap["has_impact"] = find_marker(gh.comments(cfg, n), "impact") is not None
    errs = evaluate_guards(guards, snap, reason)
    if errs:
        raise RuleError(errs)
    if target == "In Progress" and snap["status"] != BLOCKED:
        gh.assign_self(cfg, n)
    apply_status(cfg, wf, snap, target, reason)
    rollup_up(cfg, wf, snap, target)
    return target  # có thể khác target yêu cầu (Ready → Waiting khi còn blocker mở)


def rework(cfg, wf, n, reason):
    if not (reason and reason.strip()):
        raise RuleError("Cần --reason")
    snap = snapshot(cfg, n)
    stage = "review" if snap["status"] == "In Review" else "qa"
    target, count = rework_status(wf, snap["type"], snap["status"], snap["rework_count"])
    gh.set_field(cfg, snap["item_id"], "Rework Count", count)
    gh.comment(cfg, n, f"<!-- omi:rework n={count} stage={stage} -->\n🔁 Rework lần {count} ({stage}): {reason}")
    apply_status(cfg, wf, snap, "In Progress")
    if target == BLOCKED:
        apply_status(cfg, wf, snap, BLOCKED,
                     f"Vượt giới hạn rework ({wf['max_rework']}), cần người xem")
    return target


def block(cfg, wf, n, reason=None, by=None):
    snap = snapshot(cfg, n)
    if by:
        gh.add_blocked_by(cfg, n, gh.issue_db_id(cfg, by))
        if snap["status"] == WAITING:
            print(f"#{n} đã ở {WAITING}, thêm blocker #{by}")
            return WAITING
        if not reason and snap["status"] != BLOCKED and WAITING in allowed_statuses(wf, snap["type"]):
            try:
                transition(wf, snap["type"], snap["status"], WAITING)
            except RuleError:
                pass
            else:  # phụ thuộc đã lên kế hoạch → Waiting (script tự ra khi blocker xong), không Blocked
                return move(cfg, wf, n, WAITING)
        snap["open_blockers"] += 1
        reason = reason or f"blocked by #{by}"
    guards = transition(wf, snap["type"], snap["status"], BLOCKED)
    errs = evaluate_guards(guards, snap, reason)
    if errs:
        raise RuleError(errs)
    apply_status(cfg, wf, snap, BLOCKED, reason)
    return BLOCKED


def unblock(cfg, wf, n):
    snap = snapshot(cfg, n)
    if snap["status"] != BLOCKED:
        raise RuleError(f"#{n} không ở Blocked")
    prev = find_marker(gh.comments(cfg, n), "blocked-from")
    if not prev or prev is True:
        raise RuleError(f"#{n}: không tìm thấy marker blocked-from, dùng `move` với status mong muốn")
    # Ready/Waiting → xin Ready, move tự rẽ sang Waiting nếu còn blocker mở
    return move(cfg, wf, n, "Ready" if prev == WAITING else prev)
