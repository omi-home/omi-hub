"""Acceptance criteria: parse mục AC, phán quyết nghiệm thu theo test ac<n>_<i>."""
import re


def ac_section(body):
    m = re.search(r"^### Acceptance criteria\s*\n(.*?)(?=^### |\Z)", body or "", re.M | re.S)
    return m.group(1).strip() if m else ""


def parse_ac(body):
    out = []
    for line in ac_section(body).splitlines():
        m = re.match(r"\s*- \[( |x|X)\]\s*(.+)", line)
        if m:
            out.append({"i": len(out) + 1, "text": m.group(2).strip(), "checked": m.group(1) != " ",
                        "manual": "[manual]" in m.group(2).lower()})
    return out


def accept_verdict(n, acs, output, exit_code):
    """AC tự động cần test `ac<n>_<i>` xuất hiện trong output và lệnh thoát 0; AC [manual] cần được tick."""
    missing = []
    for a in acs:
        if a["manual"]:
            if not a["checked"]:
                missing.append(f"AC{a['i']} [manual] chưa tick")
        elif exit_code != 0 or f"ac{n}_{a['i']}" not in output:
            missing.append(f"AC{a['i']} thiếu hoặc fail test ac{n}_{a['i']}")
    return not missing, missing
