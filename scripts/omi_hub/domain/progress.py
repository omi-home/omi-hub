"""Tiến độ dự án và bước tiếp theo của task dở — thuần, không I/O."""
from .planning import pick_next

ACTIVE = ("In Progress", "In Review", "In QA")


def render_status(wf, items, milestone=None):
    items = [i for i in items if milestone is None or i["milestone"] == milestone]
    live = [i for i in items if i["status"] != "Cancelled"]
    kids, lines = {}, []
    for i in items:
        kids.setdefault(i["parent"], []).append(i)

    def desc(n):
        out, stack = [], list(kids.get(n, []))
        while stack:
            c = stack.pop()
            out.append(c)
            stack += kids.get(c["number"], [])
        return [x for x in out if x["status"] != "Cancelled"]

    def ratio(xs):
        d = sum(1 for x in xs if x["status"] == "Done")
        return f"{d}/{len(xs)} ({d * 100 // len(xs) if xs else 0}%)"

    def section(title, rows):
        if rows:
            lines.append(title)
            lines.extend(rows)

    tasks = [i for i in live if i["type"] in ("Task", "Bug")]
    lines.append(f"STATUS{' ' + milestone if milestone else ''}: {ratio(live)} item Done · Task/Bug {ratio(tasks)}")
    lines.append(" · ".join(f"{s} {c}" for s in wf["statuses"]
                            if (c := sum(1 for i in items if i["status"] == s))))
    for e in sorted((i for i in items if i["type"] == "Epic"), key=lambda x: x["number"]):
        lines.append(f"- #{e['number']} {e['title']} — {e['status']} · {ratio(desc(e['number']))}")
    section("Đang làm:", [f"- #{i['number']} {i['title']} — {i['status']}" for i in live if i["status"] in ACTIVE])
    section("Blocked:", [f"- #{i['number']} {i['title']} — {i['blocked_reason'] or 'blocked-by'}"
                         for i in live if i["status"] == "Blocked"])
    section("Waiting:", [f"- #{i['number']} {i['title']} — chờ " + ", ".join(f"#{b}" for b in i.get("blockers", []))
                         for i in live if i["status"] == "Waiting"])
    section("Rework:", [f"- #{i['number']} {i['title']} — {i['rework_count']} lần"
                        for i in live if i.get("rework_count")])
    nxt = pick_next(wf, items)
    lines.append(f"Tiếp theo: #{nxt['number']} {nxt['title']}" if nxt else "Tiếp theo: (không có Task/Bug Ready)")
    return "\n".join(lines)


def resume_step(status, dirty, ahead, reviewed, pack_exists):
    """Bước tiếp theo của task dở, suy ra thuần từ trạng thái (GitHub + git + .omi/tmp)."""
    if status in (None, "Done", "Cancelled"):
        return "next", "Task đã kết thúc → `start` lấy task tiếp."
    if status == "Blocked":
        return "blocked", "Task đang Blocked → báo người dùng lý do, chờ `unblock`."
    if status == "Waiting":
        return "next", "Task đang chờ issue blocked-by → `start` lấy task khác."
    if status in ("Draft", "Triage", "Approved", "Ready"):
        return "start", "Chưa bắt đầu → `start`."
    if status == "In Progress":
        if dirty or ahead == 0:
            return "code", "Đang viết code: xem `git diff --stat`, làm tiếp → `check` → commit → `submit`."
        return "submit", "Code đã commit → `check` → `submit`."
    if status == "In Review":
        if reviewed:
            return "qa", "Review đã ghi nhận → `qa`."
        return "review", ("Chưa có kết quả review → gọi reviewer với gói `.omi/tmp/review-<n>.md` rồi `review-done`."
                          if pack_exists else "Chưa có kết quả review và mất gói review → `submit` lại để sinh gói.")
    return "qa", "Đang QA → chạy lại `qa`."
