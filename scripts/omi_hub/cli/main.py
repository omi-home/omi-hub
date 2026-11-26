"""Parse tham số và gọi use case. Lệnh mới đăng ký thêm ở đây khi task tương ứng làm xong."""
import argparse
import sys
from pathlib import Path

from omi_hub.application import audit, doctor, items, pipeline, plans, release, setup, views
from omi_hub.application.workspace import load_cfg
from omi_hub.config import load_templates, load_workflow
from omi_hub.domain.errors import RuleError
from omi_hub.domain.templates import fill, skeleton
from omi_hub.infrastructure.github.client import GhError


def _num(s):
    return int(str(s).lstrip("#"))


def _nums(s):
    return [_num(x) for x in s.split(",") if x.strip()]


def build_parser():
    ap = argparse.ArgumentParser(prog="omi")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init")
    p.add_argument("--milestone")
    p.add_argument("--from-template", type=int)
    p.add_argument("--template-only", action="store_true")
    p.add_argument("--hub-repo", default="omi-home/omi-hub")
    p.add_argument("--test-cmd")
    p.add_argument("--lint-cmd")
    p.add_argument("--accept-cmd")
    p.add_argument("--repo-dir", default=".", help="repo git, tương đối với workspace (cwd)")
    sub.add_parser("doctor", help="kiểm workspace sau khi cập nhật plugin")
    p = sub.add_parser("release")
    p.add_argument("--merge", action="store_true", help="merge PR release nếu owner org đã approve")
    p = sub.add_parser("new")
    p.add_argument("type")
    p.add_argument("title")
    p.add_argument("--parent", type=_num)
    p.add_argument("--affects", type=_nums, default=[])
    p.add_argument("--milestone")
    p.add_argument("--priority")
    p.add_argument("--estimate", type=float)
    p.add_argument("--body-file")
    p.add_argument("--field", action="append", default=[], help='"Tên mục=nội dung", lặp lại được')
    p = sub.add_parser("move")
    p.add_argument("number", type=_num)
    p.add_argument("status")
    p.add_argument("--reason")
    p = sub.add_parser("rework")
    p.add_argument("number", type=_num)
    p.add_argument("--reason", required=True)
    p = sub.add_parser("block")
    p.add_argument("number", type=_num)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--reason")
    g.add_argument("--by", type=_num)
    p = sub.add_parser("unblock")
    p.add_argument("number", type=_num)
    p = sub.add_parser("tree")
    p.add_argument("number", type=_num, nargs="?")
    sub.add_parser("next")
    p = sub.add_parser("apply")
    p.add_argument("plan")
    p.add_argument("--approve", action="store_true")
    p = sub.add_parser("audit")
    p.add_argument("--fix", action="store_true")
    p = sub.add_parser("plan-show")
    p.add_argument("plan")
    p = sub.add_parser("carry", help="Task Draft cũ → finding của parent, Task → Cancelled")
    p.add_argument("numbers", type=_num, nargs="+")
    p = sub.add_parser("submit")
    p.add_argument("number", type=_num)
    p.add_argument("--findings", help="mã <p>.<i>,... đã làm trong task này")
    for name in ("context", "qa", "accept", "pr-lint"):
        sub.add_parser(name).add_argument("number", type=_num)
    p = sub.add_parser("start")
    p.add_argument("number", type=_num, nargs="?")
    sub.add_parser("check")
    p = sub.add_parser("impact")
    p.add_argument("number", type=_num)
    p.add_argument("--post", action="store_true")
    p = sub.add_parser("template")
    p.add_argument("type")
    p = sub.add_parser("status")
    p.add_argument("--milestone")
    sub.add_parser("resume")
    p = sub.add_parser("review-done")
    p.add_argument("number", type=_num)
    p.add_argument("--fail", help="blocker gộp ≤ 3 dòng → rework")
    p.add_argument("--improve", action="append", default=[], help="IMPROVE → findings của parent (lặp lại được)")
    return ap


def run(a, wf):
    if a.cmd == "init":
        setup.init(wf, a.milestone, a.from_template, a.template_only, a.hub_repo,
                   a.test_cmd, a.lint_cmd, a.accept_cmd, a.repo_dir)
        return 0
    if a.cmd == "template":
        print(skeleton(load_templates(), a.type))
        return 0
    if a.cmd == "plan-show":
        return pipeline.plan_show(wf, a.plan)
    cfg = load_cfg()
    if a.cmd in ("check", "qa", "accept", "pr-lint"):
        return {"check": lambda: pipeline.check(cfg), "qa": lambda: pipeline.qa(cfg, wf, a.number),
                "accept": lambda: pipeline.accept(cfg, wf, a.number),
                "pr-lint": lambda: pipeline.pr_lint(cfg, a.number)}[a.cmd]()
    if a.cmd == "doctor":
        return doctor.doctor(cfg)
    if a.cmd == "release":
        return release.release(cfg, a.merge)
    if a.cmd == "context":
        pipeline.context(cfg, a.number)
    elif a.cmd == "start":
        pipeline.start(cfg, wf, a.number)
    elif a.cmd == "carry":
        pipeline.carry(cfg, wf, a.numbers)
    elif a.cmd == "submit":
        pipeline.submit(cfg, wf, a.number, a.findings)
    elif a.cmd == "impact":
        pipeline.impact(cfg, a.number, a.post)
    elif a.cmd == "status":
        print(views.status(cfg, wf, a.milestone))
    elif a.cmd == "resume":
        pipeline.resume(cfg, wf)
    elif a.cmd == "review-done":
        pipeline.review_done(cfg, wf, a.number, a.fail, a.improve)
    elif a.cmd == "new":
        body = (Path(a.body_file).read_text(encoding="utf-8") if a.body_file else
                fill(load_templates(), a.type, dict(f.split("=", 1) for f in a.field)))
        items.new_item(cfg, wf, a.type, a.title, a.parent, a.affects, a.milestone, a.priority, a.estimate, body)
    elif a.cmd == "move":
        items.move(cfg, wf, a.number, a.status, a.reason)
    elif a.cmd == "rework":
        items.rework(cfg, wf, a.number, a.reason)
    elif a.cmd == "block":
        items.block(cfg, wf, a.number, a.reason, a.by)
    elif a.cmd == "unblock":
        items.unblock(cfg, wf, a.number)
    elif a.cmd == "apply":
        plans.apply(cfg, wf, a.plan, a.approve)
    elif a.cmd == "audit":
        return audit.audit(cfg, wf, a.fix)
    elif a.cmd == "tree":
        print("\n".join(views.tree(cfg, a.number)))
    elif a.cmd == "next":
        it = views.next_item(cfg, wf)
        print(f"#{it['number']} {it['title']}" if it else "Không có Task/Bug nào Ready.")
    return 0


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    a = build_parser().parse_args(argv)
    try:
        return run(a, load_workflow())
    except (RuleError, GhError, OSError, ValueError) as e:  # ValueError gồm JSONDecodeError (plan hỏng)
        print(f"❌ {e}", file=sys.stderr)
        return 2
