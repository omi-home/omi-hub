"""Chọn việc tiếp theo và kiểm plan phân rã trước khi apply."""
import re

from .errors import RuleError
from .relations import check_parent
from .templates import check_template, with_prefix


def pick_next(wf, items):
    """Task/Bug Ready, không bị chặn; ưu tiên Priority, rồi milestone đến hạn sớm, rồi số nhỏ."""
    order = {p: i for i, p in enumerate(wf["priorities"])}
    cands = [i for i in items if i["type"] in ("Task", "Bug") and i["status"] == "Ready"
             and i["state"] == "OPEN" and i["open_blockers"] == 0]
    cands.sort(key=lambda i: (order.get(i["priority"], 99), i["milestone_due"] or "9999", i["number"]))
    return cands[0] if cands else None


AC_TYPES = {"User Story", "Functional Requirement", "Non-Functional Requirement"}
_EXISTING = object()
KEY_LETTER = {"Epic": "E", "User Story": "S", "Functional Requirement": "F", "Non-Functional Requirement": "N", "Task": "T", "Bug": "B"}
KEY_RE = re.compile(r"[A-Z]\d{3}(\.[A-Z]\d{3})*")


def validate_plan(wf, plan, tpl=None):
    errs, seen = [], set()

    def walk(node, parent_type):
        k = node.get("key")
        if not k or k in seen:
            errs.append(f"key thiếu hoặc trùng: {k}")
        seen.add(k)
        t = node.get("type")
        if k and not (KEY_RE.fullmatch(k) and (t not in KEY_LETTER or k.split(".")[-1][0] == KEY_LETTER[t])):
            errs.append(f"key '{k}' phải dạng <chữ loại><NNN> nối bằng dấu chấm, ví dụ E001.S002.T003 "
                        "(E=Epic, S=User Story, F=Functional Requirement, N=Non-Functional Requirement, T=Task, B=Bug)")
        if t == "Change Request":
            errs.append(f"{k}: Change Request không tạo từ plan, dùng `new \"Change Request\" ...`")
        elif t not in wf["types"]:
            errs.append(f"{k}: loại '{t}' không thuộc workflow omi")
            return
        elif parent_type is not _EXISTING:
            try:
                check_parent(wf, t, parent_type)
            except RuleError as e:
                errs.append(f"{k}: {e}")
        if t in AC_TYPES and "acceptance criteria" not in node.get("body", "").lower():
            errs.append(f"{k}: thiếu mục '### Acceptance criteria'")
        if tpl and t in tpl:
            body = node.get("body", "")
            if node.get("affects"):
                body += "\n\n### Affects\n" + " ".join(f"#{a}" for a in node["affects"])
            title = with_prefix(tpl, t, node.get("title", ""))
            errs.extend(f"{k}: {e}" for e in check_template(tpl, t, title, body))
        if t == "Epic" and parent_type is None and not (node.get("milestone") or plan.get("milestone")):
            errs.append(f"{k}: Epic cần milestone (plan.milestone hoặc node.milestone)")
        if node.get("milestone") and parent_type is not None:
            errs.append(f"{k}: milestone chỉ đặt ở node gốc; node con kế thừa milestone của parent")
        for c in node.get("children", []):
            walk(c, t)

    for node in plan.get("items", []):
        walk(node, _EXISTING if "parent" in node else None)
    return errs
