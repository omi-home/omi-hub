"""Use case doctor: kiểm workspace sau khi cập nhật plugin. Mỗi mục một dòng OK/WARN/FAIL; có FAIL → exit 1."""
import json
import tempfile
from pathlib import Path

from omi_hub.application import setup
from omi_hub.application.workspace import repo_dir
from omi_hub.config import load_workflow
from omi_hub.infrastructure.github import gateway as gh

PLUGIN_JSON = setup.TEMPLATES.parent / ".claude-plugin" / "plugin.json"
REQUIRED = ("owner", "repo", "repo_dir", "project_number", "project_id", "fields", "default_branch", "main_branch")
INIT = "chạy lại `OMI_CLI init --repo-dir <repo>`"


class Fail(Exception):
    def __init__(self, reason, fix):
        super().__init__(f"{reason} → {fix}")


class Warn(Fail):
    pass


def _ver(s):
    return tuple(int(x) for x in s.split("."))


def _lf(p):
    return p.read_bytes().replace(b"\r\n", b"\n")


def hub_repo(settings):
    name = json.loads((PLUGIN_JSON.parent / "marketplace.json").read_text(encoding="utf-8"))["name"]
    return settings.get("extraKnownMarketplaces", {}).get(name, {}).get("source", {}).get("repo", "omi-home/omi-hub")


def check_version(hub):
    cur = json.loads(PLUGIN_JSON.read_text(encoding="utf-8"))["version"]
    latest = gh.remote_json(hub, ".claude-plugin/plugin.json")["version"]
    if _ver(cur) < _ver(latest):
        raise Fail(f"đang {cur}, mới nhất {latest}",
                   "`claude plugin marketplace update` + `claude plugin update omi-hub@<marketplace>`, khởi động lại")


def check_github_files(rendered, repo):
    want, have = rendered / ".github", repo / ".github"

    def same(p):
        q = have / p.relative_to(want)
        return q.exists() and _lf(q) == _lf(p)  # autocrlf: checkout trên Windows là CRLF
    bad = [p.relative_to(want).as_posix() for p in sorted(want.rglob("*")) if p.is_file() and not same(p)]
    if bad:
        raise Fail(f"lệch template: {', '.join(bad)}", f"{INIT} rồi commit .github/ vào develop")


def check_settings(want, have):
    missing = [k for k, v in want.get("enabledPlugins", {}).items() if have.get("enabledPlugins", {}).get(k) is not v]
    missing += [k for k in want.get("extraKnownMarketplaces", {}) if k not in have.get("extraKnownMarketplaces", {})]
    if missing:
        raise Fail(f"thiếu {', '.join(missing)}", INIT)


def check_config(cfg):
    missing = [k for k in REQUIRED if not cfg.get(k)]
    if missing:
        raise Fail(f"thiếu {', '.join(missing)}", INIT)
    if not cfg.get("commands", {}).get("test"):
        raise Fail("commands.test trống (qa không chạy test)", "`OMI_CLI init --repo-dir <repo> --test-cmd \"...\"`")


def check_fields(cfg):
    if gh.load_fields(cfg["owner"], cfg["project_number"]) != cfg["fields"]:
        raise Fail("fields khác Project trên GitHub", INIT)
    missing = [s for s in load_workflow()["statuses"] if s not in cfg["fields"]["Status"].get("options", {})]
    if missing:  # plugin mới thêm status (vd. Waiting): init thêm option, giữ Status của item
        raise Fail(f"Status thiếu option {', '.join(missing)}", INIT)


def check_variable(cfg):
    want = {k: v for k, v in cfg.items() if not k.startswith("_")}
    try:
        have = json.loads(gh.get_variable(cfg, "OMI_CONFIG"))
    except gh.GhError:
        have = None  # chưa có biến
    if have != want:
        raise Fail("biến OMI_CONFIG khác .omi/project.json (Action đọc sai cấu hình)", INIT)


def check_secret(cfg):
    if "OMI_PROJECT_TOKEN" not in gh.secret_names(cfg):
        raise Fail("chưa có secret OMI_PROJECT_TOKEN (workflow omi-audit fail)",
                   f"`gh secret set OMI_PROJECT_TOKEN -R {cfg['owner']}/{cfg['repo']}` (xem README)")


def check_branch(cfg):
    cur = gh.default_branch(cfg["owner"], cfg["repo"])
    if cur != setup.DEVELOP:
        raise Fail(f"default branch là '{cur}', cần '{setup.DEVELOP}'", INIT)


def check_ruleset(cfg):
    if not gh.has_ruleset(cfg):
        raise Warn(f"{cfg.get('main_branch') or 'nhánh chính'} không có ruleset omi-release (repo private gói Free?)",
                   f"{INIT}; không có ruleset thì chỉ merge release bằng `OMI_CLI release --merge`")


def doctor(cfg):
    root = Path(cfg.get("_root", "."))
    sp = root / ".claude" / "settings.json"
    settings = json.loads(sp.read_text(encoding="utf-8")) if sp.exists() else {}
    hub = hub_repo(settings)
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        (tmp / "repo").mkdir()
        setup.write_templates(hub, tmp / "repo", tmp)  # bản sinh từ plugin đang chạy
        want_settings = json.loads((tmp / ".claude" / "settings.json").read_text(encoding="utf-8"))
        checks = [("plugin version", lambda: check_version(hub)),
                  (".github", lambda: check_github_files(tmp / "repo", repo_dir(cfg))),
                  ("settings.json", lambda: check_settings(want_settings, settings)),
                  ("project.json", lambda: check_config(cfg)),
                  ("fields", lambda: check_fields(cfg)),
                  ("OMI_CONFIG", lambda: check_variable(cfg)),
                  ("secret", lambda: check_secret(cfg)),
                  ("default branch", lambda: check_branch(cfg)),
                  ("ruleset", lambda: check_ruleset(cfg))]
        failed = 0
        for name, fn in checks:
            try:
                fn()
                print(f"OK {name}")
            except Warn as e:
                print(f"WARN {name}: {e}")
            except Fail as e:
                failed += 1
                print(f"FAIL {name}: {e}")
            except (gh.GhError, KeyError, ValueError) as e:  # không đọc được cũng là lỗi cài đặt
                failed += 1
                print(f"FAIL {name}: {str(e).splitlines()[0]} → kiểm `gh auth status` và quyền repo")
    if not failed:  # hook SessionStart so với version plugin để nhắc chạy lại doctor sau khi cập nhật
        (root / ".omi").mkdir(exist_ok=True)
        (root / ".omi" / "doctor.json").write_text(
            json.dumps({"version": json.loads(PLUGIN_JSON.read_text(encoding="utf-8"))["version"]}), encoding="utf-8")
    return 1 if failed else 0
