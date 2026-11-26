"""Rework sau Review/QA fail, có phanh max_rework."""
import re

from .errors import RuleError
from .lifecycle import BLOCKED, allowed_statuses

REWORK_FROM = ("In Review", "In QA")


def rework(wf, type_, current, count):
    """Review/QA fail: trả (status mới, rework count mới). Vượt max_rework -> Blocked."""
    if current not in REWORK_FROM or current not in allowed_statuses(wf, type_):
        raise RuleError(f"Rework chỉ áp dụng từ In Review/In QA (hiện tại: '{current}')")
    count += 1
    return (BLOCKED if count > wf["max_rework"] else "In Progress"), count


# Lỗi hạ tầng CI (thiếu input/secret, token sai, GitHub 5xx): không phải lỗi task → không rework.
DEFAULT_CI_INFRA = [r"Input required and not supplied: \S+", r"Bad credentials",
                    r"Resource not accessible by integration", r"HTTP 5\d\d",
                    r"\b5\d\d (?:Internal Server Error|Bad Gateway|Service Unavailable|Gateway Timeout)"]


def infra_reason(log, patterns=DEFAULT_CI_INFRA):
    """Đoạn log khớp mẫu lỗi hạ tầng đầu tiên, None nếu không khớp."""
    for p in patterns:
        m = re.search(p, log or "", re.I)
        if m:
            return m.group(0)
    return None
