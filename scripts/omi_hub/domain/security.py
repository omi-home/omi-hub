"""Quyết định có cần security review không."""
import re

DEFAULT_SECURITY = ["auth", "login", "password", "secret", "token", "crypto", "permission", "acl",
                    "session", r"\.env", "sql"]


def needs_security(files, labels, parent=None, patterns=DEFAULT_SECURITY):
    if any(lb.lower() == "security" for lb in labels):
        return True
    if parent and parent.get("type") == "Non-Functional Requirement" and re.search(r"### Nhóm\s+Security", parent.get("body") or ""):
        return True
    rx = re.compile("|".join(patterns), re.I)
    return any(rx.search(f) for f in files)
