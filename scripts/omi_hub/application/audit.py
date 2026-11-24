"""Use case audit: quét Project + repo, kiểm bất biến, tự sửa được thì sửa, báo cáo vào issue OMI Audit."""
from omi_hub.domain.audit import check_invariants
from omi_hub.infrastructure.github import gateway as gh


def apply_fix(cfg, item, fix):
    kind, val = fix
    if kind == "add":
        gh.set_field(cfg, gh.add_to_project(cfg, item["id"]), "Status", val)
    elif kind == "status":
        gh.set_field(cfg, item["item_id"], "Status", val)
    elif kind == "close":
        gh.close(cfg, item["number"], "completed" if val == "Done" else "not_planned")
    elif kind == "milestone":
        gh.set_milestone(cfg, item["number"], val)


def audit(cfg, wf, fix=False):
    items = [i for i in gh.project_items(cfg) if i["title"] != gh.AUDIT_TITLE]
    by = {i["number"]: i for i in items}
    for i in gh.repo_issues(cfg):
        if i["number"] not in by and i["title"] != gh.AUDIT_TITLE:
            s = gh.issue_snapshot(cfg, i["number"])
            items.append({"number": s["number"], "id": s["id"], "type": s["type"], "in_project": False})
    lines, unfixed = [], 0
    for it in items:
        for p in check_invariants(wf, it, by):
            done = bool(fix and p["fix"])
            if done:
                apply_fix(cfg, it, p["fix"])
            unfixed += not done
            lines.append(f"- [{'x' if done else ' '}] #{p['number']}: {p['problem']}"
                         + (" (đã tự sửa)" if done else ""))
    gh.upsert_audit_issue(cfg, "\n".join(lines) if unfixed else None)
    print("\n".join(lines) or "✅ Audit sạch")
    return 1 if unfixed else 0
