"""Luật release develop→main: PO (owner của org) duyệt, nội dung PR."""

VERDICTS = ("APPROVED", "CHANGES_REQUESTED", "DISMISSED")  # COMMENTED không đổi kết luận
PO_TEAM = "org-owners"


def po_team(org):
    return f"{org}/{PO_TEAM}"


def po_approved(reviews, owners):
    """Có org owner mà kết luận mới nhất là APPROVED, và không owner nào đang CHANGES_REQUESTED."""
    owners = {o.lower() for o in owners}
    last = {}
    for r in reviews:  # theo thứ tự thời gian, như GitHub trả về
        if r["author"].lower() in owners and r["state"] in VERDICTS:
            last[r["author"].lower()] = r["state"]
    return "APPROVED" in last.values() and "CHANGES_REQUESTED" not in last.values()


def release_title(head, base, day):
    return f"[Release] {head} → {base} ({day})"


def release_body(commits, team):
    return ("### Thay đổi\n" + "\n".join(f"- {c}" for c in commits)
            + f"\n\n### Duyệt\nCần một owner của org (@{team}) approve; tự merge (merge commit) khi đủ điều kiện,"
            " hoặc `omi release --merge`.\n")
