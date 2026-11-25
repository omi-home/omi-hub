"""Luật release develop→main: PO duyệt, nội dung PR."""

VERDICTS = ("APPROVED", "CHANGES_REQUESTED", "DISMISSED")  # COMMENTED không đổi kết luận


def po_approved(reviews, po):
    """Kết luận mới nhất của PO là APPROVED (reviews theo thứ tự thời gian, như GitHub trả về)."""
    last = [r["state"] for r in reviews if r["author"].lower() == po.lower() and r["state"] in VERDICTS]
    return bool(last) and last[-1] == "APPROVED"


def release_title(head, base, day):
    return f"[Release] {head} → {base} ({day})"


def release_body(commits, po):
    return ("### Thay đổi\n" + "\n".join(f"- {c}" for c in commits)
            + f"\n\n### Duyệt\nCần @{po} approve; merge bằng merge commit (`omi release --merge`).\n")
