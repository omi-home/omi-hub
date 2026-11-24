"""Quan hệ cha–con, liên kết bắt buộc, rollup status lên parent."""
from .errors import RuleError
from .lifecycle import is_terminal, type_def


def check_parent(wf, child_type, parent_type):
    t = type_def(wf, child_type)
    if parent_type is None:
        if "parent" in t["requires"]:
            raise RuleError(f"{child_type} bắt buộc có parent ({', '.join(t['parents'])})")
        return
    if parent_type not in t["parents"]:
        allowed = ", ".join(t["parents"]) or "không có"
        raise RuleError(f"{child_type} không được làm con của {parent_type} (cho phép: {allowed})")


def check_links(wf, type_, affects_count, has_milestone):
    req = type_def(wf, type_)["requires"]
    errs = []
    if "affects" in req and affects_count == 0:
        errs.append(f"{type_} cần ít nhất 1 item Affects (--affects)")
    if "milestone" in req and not has_milestone:
        errs.append(f"{type_} cần milestone (--milestone)")
    if errs:
        raise RuleError(errs)


def rollup(wf, parent_type, parent_status, child_statuses, trigger):
    """Status mới của parent sau khi một con đổi sang `trigger`, hoặc None."""
    if trigger == "In Progress" and parent_status == "Approved":
        return "In Progress"
    target = type_def(wf, parent_type).get("on_children_done")
    if (target and parent_status == "In Progress" and child_statuses
            and all(is_terminal(wf, s) for s in child_statuses)):
        if target == "Done" and "Done" not in child_statuses:
            return None  # mọi con bị hủy: để người quyết
        return target
    return None
