"""Guard của transition: kiểm điều kiện trên snapshot issue (dict thuần)."""


def _has_reason(r):
    return bool(r and r.strip())


GUARDS = {
    "reason": lambda s, r: (_has_reason(r), "Cần --reason"),
    "parent_ready": lambda s, r: (
        bool(s["parent"]) and s["parent"]["status"] in ("Approved", "In Progress"),
        "Parent phải ở Approved hoặc In Progress"),
    "no_open_blockers": lambda s, r: (
        s["open_blockers"] == 0, f"Còn {s['open_blockers']} issue blocked-by đang mở"),
    "pr_open": lambda s, r: (
        any(p["state"] == "OPEN" for p in s["prs"]), "Cần PR đang mở có 'Closes #<số issue>'"),
    "pr_merged": lambda s, r: (any(p["merged"] for p in s["prs"]), "PR liên kết chưa merge"),
    "children_terminal": lambda s, r: (
        all(c["status"] in ("Done", "Cancelled") for c in s["children"]),
        "Còn item con chưa Done/Cancelled"),
    "impact_analysis": lambda s, r: (
        s.get("has_impact", False), "Change Request cần comment phân tích ảnh hưởng có <!-- omi:impact -->"),
    "blocker_present": lambda s, r: (
        _has_reason(r) or s["open_blockers"] > 0, "Cần --reason hoặc --by <issue chặn>"),
}


def evaluate_guards(guards, snap, reason=None):
    """Trả danh sách thông điệp lỗi (rỗng = qua hết). Guard lạ -> KeyError."""
    errs = []
    for g in guards:
        ok, msg = GUARDS[g](snap, reason)
        if not ok:
            errs.append(msg)
    return errs
