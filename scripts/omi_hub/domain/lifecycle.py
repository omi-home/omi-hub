"""Vòng đời theo loại: status hợp lệ, transition, Blocked/unblock."""
from .errors import RuleError

BLOCKED = "Blocked"
WAITING = "Waiting"  # chờ issue blocked-by kết thúc; script tự chuyển, không cần người


def _as_list(v):
    return v if isinstance(v, list) else [v]


def type_def(wf, type_):
    try:
        return wf["types"][type_]
    except KeyError:
        raise RuleError(f"Loại '{type_}' không thuộc workflow omi") from None


def allowed_statuses(wf, type_):
    t = type_def(wf, type_)
    out = {t["initial"], BLOCKED}
    for tr in t["transitions"]:
        out.update(_as_list(tr["from"]))
        out.add(tr["to"])
    return out


def check_creatable(wf, type_):
    """Loại legacy (vd. User Story): issue cũ vẫn hợp lệ nhưng không tạo mới."""
    if type_def(wf, type_).get("legacy"):
        raise RuleError(f"{type_} không còn tạo mới — dùng Functional Requirement (mục `### Story` tùy chọn)")


def is_terminal(wf, status):
    return status in wf["terminal"]


def needs_human(wf, target):
    return target in wf["human_approval"]


def transition(wf, type_, current, target, blocked_from=None):
    """Trả danh sách guard cần kiểm cho current -> target; RuleError nếu không hợp lệ."""
    if target not in allowed_statuses(wf, type_):
        raise RuleError(f"{type_} không dùng status '{target}'")
    if current == target:
        raise RuleError(f"Item đã ở '{target}'")
    if is_terminal(wf, current):
        raise RuleError(f"'{current}' là trạng thái kết thúc, không chuyển tiếp được")
    if target == BLOCKED:
        return ["blocker_present"]
    if current == BLOCKED:
        if target != blocked_from:
            raise RuleError(f"Unblock chỉ được về trạng thái trước khi block ('{blocked_from}')")
        return ["no_open_blockers"]
    for tr in type_def(wf, type_)["transitions"]:
        if current in _as_list(tr["from"]) and tr["to"] == target:
            return list(tr.get("guards", []))
    raise RuleError(f"{type_}: không được chuyển '{current}' → '{target}'")
