"""Template chuẩn issue/PR: parse mục, kiểm title/body, dựng body, in khung."""
import re

from .errors import RuleError

_EMPTY = {"", "_No response_"}


def sections(body):
    out, cur = {}, None
    for line in (body or "").splitlines():
        m = re.match(r"^### (.+?)\s*$", line)
        if m:
            cur = m.group(1)
            out[cur] = []
        elif cur:
            out[cur].append(line)
    clean = {k: re.sub(r"<!--.*?-->", "", "\n".join(v), flags=re.S).strip() for k, v in out.items()}
    return {k: ("" if v in _EMPTY else v) for k, v in clean.items()}  # comment gợi ý = chưa điền


def prefix(type_):
    return f"[{type_}] "


def with_prefix(tpl, type_, title):
    tpl[type_]  # KeyError nếu loại không có template
    title = (title or "").strip()
    return title if title.startswith(prefix(type_)) else prefix(type_) + title


def _check_sections(spec, body):
    errs, secs = [], sections(body)
    for s in spec:
        h, v = s["heading"], secs.get(s["heading"], "")
        if not v or (s.get("placeholder", True) and v == s.get("default", "").strip()):
            if s["required"]:
                errs.append(f"Thiếu mục '### {h}'")
            continue
        if s.get("checklist") and not re.search(r"^\s*- \[[ xX]\] \S", v, re.M):
            errs.append(f"Mục '{h}' phải là checklist '- [ ] ...'")
        if s.get("options") and v not in s["options"]:
            errs.append(f"Mục '{h}' phải là một trong: {', '.join(s['options'])}")
        if s.get("pattern") and not re.search(s["pattern"], v, re.M):
            errs.append(f"Mục '{h}' sai định dạng ({s.get('hint') or s['pattern']})")
    return errs


def check_template(tpl, type_, title, body):
    t, title, errs, p = tpl[type_]["title"], title or "", [], prefix(type_)
    if not title.startswith(p):
        errs.append(f"Title {type_} phải bắt đầu bằng '{p.strip()}' (viết đầy đủ, không viết tắt)")
    rest = title[len(p):] if title.startswith(p) else title
    if not re.match(t["pattern"], rest):
        errs.append(f"Title {type_} phải theo mẫu '{p}{t['hint']}' (ví dụ: {p}{t['example']})")
    return errs + _check_sections(tpl[type_]["sections"], body)


def check_pr(pr_tpl, title, body):
    t = pr_tpl["title"]
    errs = [] if re.match(t["pattern"], title or "") else [
        f"Title PR phải theo mẫu '{t['hint']}' (ví dụ: {t['example']})"]
    return errs + _check_sections(pr_tpl["sections"], body)


def fill(tpl, type_, fields):
    """Dựng body từ {heading: value}; mục không truyền mà có default thật (placeholder=false) dùng default."""
    unknown = set(fields) - {s["heading"] for s in tpl[type_]["sections"]}
    if unknown:
        raise RuleError(f"{type_} không có mục: {', '.join(sorted(unknown))}")
    parts = []
    for s in tpl[type_]["sections"]:
        v = fields.get(s["heading"]) or (s.get("default") if s.get("placeholder", True) is False else None)
        if v:
            parts.append(f"### {s['heading']}\n{v.strip()}")
    return "\n\n".join(parts)


def skeleton(tpl, type_):
    t = tpl[type_]
    p = prefix(type_)
    lines = [f"Title: {p}{t['title']['hint']}  (ví dụ: {p}{t['title']['example']})",
             "(CLI tự thêm prefix nếu thiếu)", ""]
    for s in t["sections"]:
        mark = "" if s["required"] else " (tùy chọn)"
        lines += [f"### {s['heading']}{mark}",
                  s.get("default") or ("|".join(s["options"]) if s.get("options") else f"<{s.get('hint', '')}>"), ""]
    return "\n".join(lines).rstrip() + "\n"
