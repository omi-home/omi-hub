"""Use case release: PR develop→main, merge khi PO approve."""
import datetime

from omi_hub.domain.errors import RuleError
from omi_hub.domain.release import po_approved, release_body, release_title
from omi_hub.infrastructure.github import gateway as gh


def release(cfg, merge=False):
    po, main, dev = cfg.get("po"), cfg.get("main_branch"), cfg.get("default_branch")
    if not (po and main):
        raise RuleError("Chưa bật luồng release: chạy lại `init --po <login>`")
    pr = gh.open_pr_for_branch(cfg, dev)
    if merge:
        if pr is None:
            raise RuleError(f"Không có PR {dev}→{main} đang mở — chạy `release` trước")
        if not po_approved(gh.pr_reviews(cfg, pr), po):
            print(f"RELEASE WAIT PR #{pr} chưa có approve của @{po}")
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
                          release_body(commits, po), dev, base=main, reviewer=po)
        try:  # có ruleset: GitHub tự merge ngay khi PO approve
            gh.merge_pr(cfg, pr, release=True, auto=True)
        except gh.GhError:
            pass  # không có ruleset/auto-merge: merge bằng `release --merge`
    print(f"RELEASE PR #{pr} chờ @{po} approve → tự merge nếu có ruleset, không thì `release --merge`")
    return 0
