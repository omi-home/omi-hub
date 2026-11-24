"""Lớp thấp nhất: chạy gh, GraphQL, REST, thông báo lỗi có gợi ý."""
import json
import subprocess

HINTS = [
    ("insufficient_scopes", "Thiếu scope: chạy `gh auth refresh -s project,admin:org`"),
    ("gh auth login", "Chưa đăng nhập: chạy `gh auth login`"),
    ("rate limit", "Hết rate limit GitHub, thử lại sau"),
]


class GhError(Exception):
    pass


def run(args, input=None, cwd=None):
    p = subprocess.run(["gh", *args], input=input, capture_output=True, text=True, encoding="utf-8", cwd=cwd)
    if p.returncode != 0:
        msg = (p.stderr or p.stdout).strip()
        hint = next((h for k, h in HINTS if k in msg.lower()), "")
        raise GhError(f"gh {' '.join(args[:3])}: {msg}" + (f"\n→ {hint}" if hint else ""))
    return p.stdout


def graphql(query, **variables):
    out = json.loads(run(["api", "graphql", "--input", "-"],
                         json.dumps({"query": query, "variables": variables})))
    if out.get("errors"):
        raise GhError("; ".join(e["message"] for e in out["errors"]))
    return out["data"]


def rest(method, path, body=None):
    args = ["api", "-X", method, path, "-H", "Accept: application/vnd.github+json"]
    if body is not None:
        args += ["--input", "-"]
    out = run(args, json.dumps(body) if body is not None else None)
    return json.loads(out) if out.strip() else None


def repo_path(cfg):
    return f"repos/{cfg['owner']}/{cfg['repo']}"


def repo_full(cfg):
    return f"{cfg['owner']}/{cfg['repo']}"
