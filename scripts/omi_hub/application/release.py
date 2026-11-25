"""Use case release: PR develop→main, merge khi owner của org (PO) approve."""
import datetime

from omi_hub.domain.errors import RuleError
from omi_hub.domain.release import PO_TEAM, po_approved, po_team, release_body, release_title
from omi_hub.infrastructure.github import gateway as gh


def sync_po_team(cfg):
    """Team org-owners = đúng danh sách owner của org (owner thay đổi thì lần chạy sau tự khớp). Trả owners."""
    owners = set(gh.org_owners(cfg["owner"]))
    gh.ensure_team(cfg, PO_TEAM)
    current = set(gh.team_members(cfg, PO_TEAM))
    for u in sorted(owners - current):
        gh.add_team_member(cfg, PO_TEAM, u)
    for u in sorted(current - owners):
        gh.remove_team_member(cfg, PO_TEAM, u)
    return owners


def release(cfg, merge=False):
    main, dev = cfg.get("main_branch"), cfg.get("default_branch")
    if not main:
        raise RuleError("Chưa bật luồng release: chạy lại `init`")
    team = po_team(cfg["owner"])
    owners = sync_po_team(cfg)
    pr = gh.open_pr_for_branch(cfg, dev)
    if merge:
        if pr is None:
            raise RuleError(f"Không có PR {dev}→{main} đang mở — chạy `release` trước")
        if not po_approved(gh.pr_reviews(cfg, pr), owners):
            print(f"RELEASE WAIT PR #{pr} chưa có approve của owner org (@{team})")
            return 1
        gh.merge_pr(cfg, pr, release=True)
        print(f"RELEASED PR #{pr} {dev}→{main}")
        return 0
    if pr is None:
        commits = gh.compare_commits(cfg, main, dev)
        if not commits:
            print(f"NOTHING {dev} không có commit mới so với {main}")
            return 0
        pr = gh.create_pr(cfg, release_title(dev, main, datetime.date.today().isoformat()),
                          release_body(commits, team), dev, base=main, reviewer=team)
        try:  # có ruleset: GitHub tự merge ngay khi owner org approve
            gh.merge_pr(cfg, pr, release=True, auto=True)
        except gh.GhError:
            pass  # không có ruleset/auto-merge: merge bằng `release --merge`
    print(f"RELEASE PR #{pr} chờ owner org (@{team}) approve → tự merge nếu có ruleset, không thì `release --merge`")
    return 0
