"""Use case handoff: script sinh mục tự động của `.omi/HANDOFF.md` và quản lý ghi chú phiên."""
import contextlib
import io
import json
from datetime import date, datetime
from pathlib import Path

from omi_hub.application import doctor, feedback
from omi_hub.application.workspace import tmp_dir
from omi_hub.domain import findings
from omi_hub.domain import handoff as hd
from omi_hub.domain.planning import pick_next
from omi_hub.infrastructure.github import gateway as gh

CLOSED = ("Done", "Cancelled")


def _path(cfg):
    return Path(cfg.get("_root", ".")) / ".omi" / "HANDOFF.md"


def _write(p, doc):
    """Ghi qua file tạm rồi replace: lỗi giữa chừng không làm hỏng HANDOFF."""
    p.parent.mkdir(parents=True, exist_ok=True)
    t = p.with_suffix(".md.tmp")
    t.write_text(doc, encoding="utf-8")
    t.replace(p)


def _doctor_summary(cfg):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        doctor.doctor(cfg)
    rows = buf.getvalue().splitlines()
    count = {k: sum(r.startswith(k + " ") for r in rows) for k in ("OK", "WARN", "FAIL")}
    bad = [r for r in rows if r.startswith(("WARN ", "FAIL "))]
    return " · ".join(f"{k} {v}" for k, v in count.items()) + "".join(f"\n  - {r}" for r in bad)


def _queue_len(cfg):
    q = feedback._queue(cfg)
    return sum(1 for x in q.read_text(encoding="utf-8").splitlines() if x.strip()) if q.exists() else 0


def handoff(cfg, wf, today=None, doctor_summary=_doctor_summary):
    p = _path(cfg)
    doc = p.read_text(encoding="utf-8") if p.exists() else "# HANDOFF\n"
    try:
        its = [i for i in gh.project_items(cfg) if i["title"] != gh.AUDIT_TITLE]
        epics = [i for i in its if i["type"] == "Epic" and i["status"] != "Cancelled"]
        fnd = [f"[{c}] {t}" for e in epics
               for c, t in findings.open_codes(e["number"], findings.parse(gh.marked_comment(cfg, e["number"], findings.NAME)[1]))]
        doc_sum = doctor_summary(cfg)
    except gh.GhError as e:  # lỗi mạng: chỉ cảnh báo, giữ nguyên file
        print(f"HANDOFF WARN: không đọc được GitHub ({str(e).splitlines()[0]}), giữ nguyên {p.name}")
        return 1
    by = {i["number"]: i for i in its}
    cur = tmp_dir(cfg) / "current"
    cur_n = int(cur.read_text(encoding="utf-8").strip()) if cur.exists() else None
    label = lambda n: f"#{n} {by[n]['title']} — {by[n]['status']}" if n in by else f"#{n}"  # noqa: E731
    done = {i["number"] for i in its if i["status"] == "Done"}
    seen = hd.done_seen(doc)
    nxt = pick_next(wf, its)
    auto = hd.render_auto(
        json.loads(feedback.PLUGIN_JSON.read_text(encoding="utf-8"))["version"], doc_sum,
        label(cur_n) if cur_n else None, label(nxt["number"]) if nxt else None,
        None if seen is None else [label(n) for n in sorted(done - seen)],
        [label(i["number"]) for i in sorted(its, key=lambda x: x["number"]) if i["status"] in ("Draft", "Triage")],
        fnd, _queue_len(cfg), done, datetime.now().strftime("%Y-%m-%d %H:%M"))
    doc = hd.put_block(doc, hd.AUTO, auto)
    doc, removed = hd.prune_notes(doc, {n for n, i in by.items() if i["status"] in CLOSED}, today or date.today())
    _write(p, doc)
    print(f"HANDOFF {p.as_posix()}" + (f" (xoá {removed} ghi chú cũ)" if removed else ""))
    return 0


def note(cfg, text, today=None):
    p = _path(cfg)
    doc = p.read_text(encoding="utf-8") if p.exists() else "# HANDOFF\n"
    _write(p, hd.add_note(doc, text, today or date.today()))
    print(f"HANDOFF NOTE {p.as_posix()}")
