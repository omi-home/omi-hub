"""Rework sau Review/QA fail, có phanh max_rework."""
from .errors import RuleError
from .lifecycle import BLOCKED, allowed_statuses

REWORK_FROM = ("In Review", "In QA")


def rework(wf, type_, current, count):
    """Review/QA fail: trả (status mới, rework count mới). Vượt max_rework -> Blocked."""
    if current not in REWORK_FROM or current not in allowed_statuses(wf, type_):
        raise RuleError(f"Rework chỉ áp dụng từ In Review/In QA (hiện tại: '{current}')")
    count += 1
    return (BLOCKED if count > wf["max_rework"] else "In Progress"), count
