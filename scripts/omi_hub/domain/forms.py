"""Render template sang định dạng GitHub: issue form YAML, PR template markdown (thuần)."""
import json

from .templates import prefix


def _q(s):
    return json.dumps(s, ensure_ascii=False)  # chuỗi/list JSON là scalar/flow YAML hợp lệ


def form_filename(type_):
    return type_.lower().replace(" ", "-") + ".yml"


def render_form(type_, t):
    lines = [f"name: {_q(type_)}", f"description: {_q(t['title']['hint'])}", f"type: {_q(type_)}"]
    lines.append(f"title: {_q(prefix(type_) + t['title'].get('prefill', ''))}")
    lines.append("body:")
    for i, s in enumerate(t["sections"], 1):
        kind = "dropdown" if s.get("options") else ("input" if s["heading"] == "Affects" else "textarea")
        lines += [f"  - type: {kind}", f"    id: s{i}", "    attributes:", f"      label: {_q(s['heading'])}"]
        if s.get("hint"):
            lines.append(f"      description: {_q(s['hint'])}")
        if s.get("options"):
            lines.append(f"      options: {_q(s['options'])}")
        elif s.get("default") and kind == "textarea":
            lines.append(f"      value: {_q(s['default'])}")
        lines += ["    validations:", f"      required: {'true' if s['required'] else 'false'}"]
    return "\n".join(lines) + "\n"


def render_pr_template(pr_tpl):
    """`.github/pull_request_template.md` cho PR tạo tay; gợi ý nằm trong comment nên chưa điền = trống."""
    t = pr_tpl["title"]
    out = [f"<!-- Title: {t['hint']} — ví dụ: {t['example']} -->", ""]
    for s in pr_tpl["sections"]:
        if s.get("default"):
            val = s["default"]
        elif s.get("options"):
            val = "<!-- chọn một: " + " | ".join(s["options"]) + " -->"
        else:
            val = f"<!-- {s.get('hint', '')} -->"
        out += [f"### {s['heading']}", val, ""]
    return "\n".join(out).rstrip() + "\n"
