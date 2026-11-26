"""Hook omi-hub. `pre`: chặn đi tắt / hỏi khi chốt baseline. `session`: in OMI_CLI + nạp context task."""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

DENY = [
    (re.compile(r"\bgh\s+issue\s+(close|reopen)\b"), "Dùng `OMI_CLI move <n> Done|Cancelled` thay cho gh issue close/reopen"),
    (re.compile(r"\bgh\s+project\s+item-edit\b"), "Dùng `OMI_CLI move` để đổi Status/field của item"),
    (re.compile(r"updateProjectV2ItemFieldValue"), "Dùng `OMI_CLI move` thay cho mutation trực tiếp"),
]
ASK = [
    (re.compile(r"omi\.py[\"']?\s+move\s+#?\d+\s+[\"']?Approved\b"), "Chốt baseline (Approved) cần người xác nhận"),
    (re.compile(r"omi\.py[\"']?\s+apply\b.*--approve"), "Apply plan với --approve sẽ chốt baseline, cần người xác nhận"),
] + [(re.compile(rx), f"Repo cài omi-hub: issue/GitHub Project chỉ thao tác qua OMI_CLI — dùng {hint}; "
                      "thiếu lệnh → báo người dùng, đề xuất issue omi-hub") for rx, hint in [
    (r"\bgh\s+issue\s+create\b", "`OMI_CLI new <Type> \"<title>\" --parent <n>`"),
    (r"\bgh\s+issue\s+edit\b", "`OMI_CLI edit <n> --field \"Mục=nội dung\"`"),
    (r"\bgh\s+issue\s+comment\b.*--edit-last", "`OMI_CLI edit` (nội dung thuộc body issue)"),
    (r"\bgh\s+issue\s+(delete|transfer)\b", "`OMI_CLI move <n> Cancelled`"),
    (r"\bgh\s+project\s+(item-add|item-delete|item-archive|field-[\w-]+)\b",
     "`OMI_CLI audit --fix` / `OMI_CLI move` / `OMI_CLI init`"),
    (r"\b(addProjectV2ItemById|deleteProjectV2Item)\b", "`OMI_CLI new` / `OMI_CLI audit --fix`"),
    (r"\baddSubIssue\b", "`OMI_CLI new ... --parent <n>`"),
    (r"\baddBlockedBy\b", "`OMI_CLI block <n> --by <m>` / `OMI_CLI new ... --blocked-by <m>`"),
]]

# Nội dung heredoc và giá trị --body/-b chỉ là văn bản, không phải lệnh → bỏ trước khi so mẫu.
_HEREDOC = re.compile(r"<<-?\s*(['\"]?)(\w+)\1[^\n]*\n.*?^\s*\2\s*$", re.S | re.M)
_HERESTRING = re.compile(r"@(['\"])\r?\n.*?\r?\n\1@", re.S)  # PowerShell @'...'@
_BODY = re.compile(r"(?<!S)(--body|-b)(=|\s+)(\"(?:\\.|[^\"\\])*\"|'[^']*'|\S+)")


def command_part(command):
    return _BODY.sub(r"\1", _HERESTRING.sub("@here", _HEREDOC.sub("<<heredoc", command)))


def decide(command):
    command = command_part(command)
    for rx, why in DENY:
        if rx.search(command):
            return "deny", why
    for rx, why in ASK:
        if rx.search(command):
            return "ask", why
    return None


def _run(args, cwd):
    p = subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.stdout.strip() if p.returncode == 0 else ""


def _find_root(cwd):
    p = Path(cwd).resolve()
    return next((d for d in (p, *p.parents) if (d / ".omi" / "project.json").exists()), None)


def session_text(plugin_root, cwd, source="startup", run=_run):
    """Dòng OMI_CLI; sau startup/clear tự nạp context task đang làm (hoặc task kế tiếp) bằng script."""
    script = Path(plugin_root) / "scripts" / "omi.py"
    root = _find_root(cwd)  # workspace chứa .omi/ (spec D12)
    head = f'OMI_CLI: python "{script}" | ' + (
        "workspace omi sẵn sàng" if root else "chưa init (OMI_CLI init --repo-dir <repo> từ workspace)")
    if root:
        head += ("\nQUY TẮC: issue/GitHub Project chỉ thao tác qua OMI_CLI (không gh issue/project trực tiếp);"
                 " thiếu lệnh → báo người dùng, đề xuất issue omi-hub")
    if not root or source not in ("startup", "clear"):
        return head
    cur = root / ".omi" / "tmp" / "current"
    if cur.exists():  # task dở (kể cả phiên trước dừng vì chạm limit): script tính bước tiếp + context
        out = run([sys.executable, str(script), "resume"], root)
        return f"{head}\n{out}\n(Tiếp tục bằng skill omi-resume; không cần chạy lại resume/context)"
    nxt = run([sys.executable, str(script), "next"], root)
    return f"{head}\nNEXT: {nxt}" if nxt else head


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "pre":
        data = json.load(sys.stdin)
        d = decide(data.get("tool_input", {}).get("command", ""))
        if d:
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                                     "permissionDecision": d[0],
                                                     "permissionDecisionReason": d[1]}}, ensure_ascii=False))
    elif mode == "session":
        try:
            source = json.load(sys.stdin).get("source", "startup")
        except (ValueError, OSError):
            source = "startup"
        root = os.environ.get("CLAUDE_PLUGIN_ROOT") or Path(__file__).resolve().parents[1]
        print(session_text(root, Path.cwd(), source))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
