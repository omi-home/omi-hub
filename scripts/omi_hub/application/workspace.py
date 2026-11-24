"""Định vị workspace và nạp .omi/project.json (spec D12)."""
import json
import os
from pathlib import Path

from omi_hub.domain.errors import RuleError


def find_root(start=None):
    """Thư mục workspace chứa .omi/project.json, tìm từ start (mặc định cwd) lên trên."""
    p = Path(start or Path.cwd()).resolve()
    return next((d for d in (p, *p.parents) if (d / ".omi" / "project.json").exists()), None)


def load_cfg():
    """Cấu hình ở workspace; trong CI repo không có .omi/ nên đọc biến OMI_CONFIG."""
    root = find_root()
    if root:
        cfg = json.loads((root / ".omi" / "project.json").read_text(encoding="utf-8"))
    elif os.environ.get("OMI_CONFIG"):
        root, cfg = Path.cwd(), json.loads(os.environ["OMI_CONFIG"])
        cfg["repo_dir"] = "."  # CI: cwd chính là repo
    else:
        raise RuleError("Không thấy .omi/project.json của workspace — chạy `OMI_CLI init --repo-dir <repo>` từ workspace")
    cfg["_root"] = str(root)
    return cfg


def repo_dir(cfg):
    return Path(cfg.get("_root", ".")) / cfg.get("repo_dir", ".")


def tmp_dir(cfg):
    return Path(cfg.get("_root", ".")) / ".omi" / "tmp"
