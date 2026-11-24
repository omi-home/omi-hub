"""Parse tham số và gọi use case. Lệnh mới đăng ký thêm ở đây khi task tương ứng làm xong."""
import argparse
import sys
from pathlib import Path

from omi_hub.application import items, views
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
    p = sub.add_parser("template")
    p.add_argument("type")
    return ap


def run(a, wf):
    if a.cmd == "template":
        print(skeleton(load_templates(), a.type))
        return 0
    cfg = load_cfg()
    if a.cmd == "new":
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
    except (RuleError, GhError) as e:
        print(f"❌ {e}", file=sys.stderr)
        return 2
