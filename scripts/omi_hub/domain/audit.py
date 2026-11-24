"""Bất biến trên trạng thái hiện tại của Project (dùng cho audit)."""
from .errors import RuleError
from .lifecycle import BLOCKED, allowed_statuses, is_terminal
from .relations import check_parent


def check_invariants(wf, item, by_number):
    """Bất biến trên trạng thái hiện tại (dùng cho audit)."""
    out = []
    n, t = item["number"], item["type"]

    def bad(problem, fix=None):
        out.append({"number": n, "problem": problem, "fix": fix})

    if t not in wf["types"]:
        bad(f"chưa có Issue Type omi hợp lệ (hiện: {t})")
        return out
    if not item["in_project"]:
        bad("chưa có trong Project", ("add", wf["types"][t]["initial"]))
        return out
    st = item["status"]
    if st not in allowed_statuses(wf, t):
        bad(f"status '{st}' không hợp lệ cho {t}")
    parent = by_number.get(item["parent"]) if item["parent"] else None
    if parent or not item["parent"]:
        try:
            check_parent(wf, t, parent["type"] if parent else None)
        except RuleError as e:
            bad(str(e))
    closed = item["state"] == "CLOSED"
    if closed and not is_terminal(wf, st):
        bad(f"issue đã đóng nhưng Status là '{st}'",
            ("status", "Cancelled" if item["state_reason"] == "NOT_PLANNED" else "Done"))
    if not closed and is_terminal(wf, st):
        bad(f"Status '{st}' nhưng issue còn mở", ("close", st))
    if st == "Done" and any(c["parent"] == n and not is_terminal(wf, c["status"]) for c in by_number.values()):
        bad("Done nhưng còn con chưa kết thúc")
    if st == BLOCKED and not item["blocked_reason"] and item["open_blockers"] == 0:
        bad("Blocked nhưng không có Blocked Reason hay blocked-by")
    if parent and parent["milestone"] and item["milestone"] != parent["milestone"]:
        bad(f"milestone '{item['milestone']}' khác parent '{parent['milestone']}'", ("milestone", parent["milestone"]))
    return out
