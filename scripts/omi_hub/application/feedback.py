"""Use case feedback: agent ghi improvement/bug của plugin thành issue ở repo omi-hub; lỗi gửi → hàng đợi cục bộ."""
import json
import re
from pathlib import Path

from omi_hub.infrastructure.github import gateway as gh

PLUGIN_JSON = Path(__file__).resolve().parents[3] / ".claude-plugin" / "plugin.json"
LABEL = "omi-feedback"


def plugin_info():
    """(cfg repo plugin {owner, repo}, version) từ plugin.json."""
    meta = json.loads(PLUGIN_JSON.read_text(encoding="utf-8"))
    owner, repo = re.search(r"github\.com[/:]([^/]+)/([^/.]+)", meta["repository"]).groups()
    return {"owner": owner, "repo": repo}, meta["version"]


def _queue(cfg):
    return Path(cfg.get("_root", ".")) / ".omi" / "feedback-queue.jsonl"


def _send(hub, entry):
    """Gửi một feedback: trùng title đang mở → comment +1; trả (số issue, trùng?)."""
    n = gh.open_issue_by_title(hub, entry["title"])
    if n:
        gh.comment(hub, n, f"+1 từ `{entry['source']}` (plugin {entry['version']})"
                   + (f"\n\n{entry['body']}" if entry.get("body") else ""))
        return n, True
    body = "\n".join([f"- Project nguồn: `{entry['source']}`", f"- Plugin: {entry['version']}",
                      f"- Loại: {entry['kind']}", f"- Lệnh liên quan: {entry.get('cmd') or '(không rõ)'}",
                      "", entry.get("body") or ""]).rstrip() + "\n"
    return gh.create_issue(hub, entry["title"], body, None, labels=[LABEL])["number"], False


def flush(cfg, hub=None):
    """Gửi lại hàng đợi; mục lỗi giữ lại. Trả số mục đã gửi."""
    q = _queue(cfg)
    if not q.exists():
        return 0
    hub = hub or plugin_info()[0]
    left, sent = [], 0
    for line in q.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            n, dup = _send(hub, json.loads(line))
            print(f"FEEDBACK #{n}" + (" (trùng)" if dup else "") + " (từ hàng đợi)")
            sent += 1
        except gh.GhError:
            left.append(line)
    if left:
        q.write_text("\n".join(left) + "\n", encoding="utf-8")
    else:
        q.unlink()
    return sent


def feedback(cfg, title, body=None, kind="improve", cmd=None):
    hub, version = plugin_info()
    entry = {"title": title, "body": body, "kind": kind, "cmd": cmd,
             "source": f"{cfg.get('owner')}/{cfg.get('repo')}", "version": version}
    flush(cfg, hub)
    try:
        n, dup = _send(hub, entry)
    except gh.GhError as e:  # không quyền/mạng/5xx: giữ lại, lần feedback/doctor sau gửi
        q = _queue(cfg)
        q.parent.mkdir(parents=True, exist_ok=True)
        with q.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        print(f"FEEDBACK QUEUED ({str(e).splitlines()[0]})")
        return None
    print(f"FEEDBACK #{n}" + (" (trùng)" if dup else ""))
    return n
