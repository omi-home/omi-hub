"""Use case init: bootstrap Issue Types, Project, fields; ghi template vào repo và workspace."""
import json
from pathlib import Path

from omi_hub.config import load_pr_template, load_templates
from omi_hub.domain.errors import RuleError
from omi_hub.domain.security import DEFAULT_SECURITY
from omi_hub.domain.forms import form_filename, render_form, render_pr_template
from omi_hub.domain.text import merge_agents_md
from omi_hub.infrastructure.github import gateway as gh

CONFIG = Path(".omi") / "project.json"  # tương đối với workspace (cwd khi chạy init)
TEMPLATES = Path(__file__).resolve().parents[3] / "templates"


def write_templates(hub_repo, repo=Path("."), workspace=Path(".")):
    """Repo chỉ nhận `.github/` (GitHub bắt buộc nằm trong repo); AGENTS.md ghi ra workspace (spec D12)."""
    forms = repo / ".github" / "ISSUE_TEMPLATE"
    forms.mkdir(parents=True, exist_ok=True)
    (forms / "config.yml").write_text((TEMPLATES / "ISSUE_TEMPLATE" / "config.yml").read_text(encoding="utf-8"),
                                      encoding="utf-8")
    for type_, t in load_templates().items():
        (forms / form_filename(type_)).write_text(render_form(type_, t), encoding="utf-8")
    (repo / ".github" / "pull_request_template.md").write_text(render_pr_template(load_pr_template()),
                                                                encoding="utf-8")
    wfdir = repo / ".github" / "workflows"
    wfdir.mkdir(parents=True, exist_ok=True)
    audit = (TEMPLATES / "workflows" / "omi-audit.yml").read_text(encoding="utf-8")
    (wfdir / "omi-audit.yml").write_text(audit.replace("__OMI_HUB_REPO__", hub_repo), encoding="utf-8")
    agents = workspace / "AGENTS.md"
    old = agents.read_text(encoding="utf-8") if agents.exists() else ""
    agents.write_text(merge_agents_md(old, (TEMPLATES / "AGENTS.md").read_text(encoding="utf-8")),
                      encoding="utf-8")


DEVELOP = "develop"
MAIN_CANDIDATES = ("main", "master")


def main_branch(cfg, old):
    if old.get("main_branch"):
        return old["main_branch"]
    current = gh.default_branch(cfg["owner"], cfg["repo"])
    if current != DEVELOP:
        return current
    found = next((b for b in MAIN_CANDIDATES if gh.branch_exists(cfg, b)), None)  # mất config, default đã là develop
    if not found:
        raise RuleError(f"Không xác định được nhánh chính (không có {'/'.join(MAIN_CANDIDATES)}); "
                        "ghi \"main_branch\" vào .omi/project.json rồi chạy lại init")
    return found


def release_flow(cfg, po, old):
    """develop = default branch (PR task, Closes #n giữ nguyên); nhánh chính chỉ nhận PR release có PO duyệt.
    Trả danh sách cảnh báo."""
    main, warns = main_branch(cfg, old), []
    try:
        gh.ensure_codeowners(cfg, main, po)  # trước ruleset: sau đó nhánh chính không nhận push thẳng
    except gh.GhError as e:  # đổi PO khi ruleset đã có: đi qua develop, PO cũ duyệt release kế tiếp
        if "rule violation" not in str(e).lower():
            raise  # thiếu quyền, mạng...: không che lỗi thật
        gh.ensure_branch(cfg, DEVELOP, main)
        gh.ensure_codeowners(cfg, DEVELOP, po)
        warns.append(f"CODEOWNERS @{po} ghi lên {DEVELOP}; lên {main} ở release kế tiếp (PO cũ approve)")
    gh.ensure_branch(cfg, DEVELOP, main)
    gh.set_default_branch(cfg, DEVELOP)
    cfg.update(default_branch=DEVELOP, main_branch=main, po=po)
    err = gh.ensure_ruleset(cfg, main)
    if err:
        warns.append(f"Không tạo được ruleset cho {main} ({err}). Repo private gói Free không có ruleset:"
                     " chỉ `release --merge` kiểm PO approve, merge tay trên web vẫn lọt.")
    return warns


def init(wf, milestone=None, from_template=None, template_only=False, hub_repo="omi-home/omi-hub",
             test_cmd=None, lint_cmd=None, accept_cmd=None, repo_dir_=".", po=None):
    """Chạy từ thư mục workspace; repo_dir_ = đường dẫn repo git tương đối với workspace."""
    old = json.loads(CONFIG.read_text(encoding="utf-8")) if CONFIG.exists() else {}
    po = po or old.get("po")
    if not template_only and not po:
        raise RuleError("Thiếu --po <login GitHub của PO> (người approve PR release develop→main)")
    owner, repo = gh.current_repo(cwd=repo_dir_)
    gh.ensure_issue_types(owner, list(wf["types"]))
    title = "OMI Template" if template_only else f"{repo} — omi"
    number = gh.find_project(owner, title)
    if number is None:
        number = gh.copy_project(owner, from_template, title) if from_template else gh.create_project(owner, title)
    gh.ensure_fields(owner, number, wf)
    if template_only:
        print(f"✅ Project mẫu #{number}. Tạo views theo docs/views.md của omi-hub.")
        return
    gh.link_project(owner, number, f"{owner}/{repo}")
    new_cmds = {"test": test_cmd, "lint": lint_cmd, "accept": accept_cmd}
    cfg = {"owner": owner, "repo": repo, "repo_dir": repo_dir_, "project_number": number,
           "project_id": gh.project_node_id(owner, number), "fields": gh.load_fields(owner, number),
           "commands": {**old.get("commands", {}), **{k: v for k, v in new_cmds.items() if v}},
           "security_paths": old.get("security_paths", DEFAULT_SECURITY),
           "review_max_diff_lines": old.get("review_max_diff_lines", 1500)}
    warns = release_flow(cfg, po, old)
    CONFIG.parent.mkdir(exist_ok=True)
    CONFIG.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_templates(hub_repo, Path(repo_dir_), Path("."))
    gh.set_variable(cfg, "OMI_CONFIG", json.dumps(cfg, ensure_ascii=False))  # Action không có .omi/ của workspace
    gh.ensure_label(cfg, "security")  # label bật security review (spec 5.6)
    if milestone:
        gh.ensure_milestone(cfg, milestone)
    for w in warns:
        print(f"⚠️ {w}")
    print(f"✅ Project #{number} đã gắn với {owner}/{repo}.\n"
          "Việc còn lại cho người:\n"
          "  1. Tạo secret OMI_PROJECT_TOKEN (fine-grained PAT: org Projects RW; repo Issues RW, Pull requests R;"
          f" Contents R cho {hub_repo}).\n"
          f"  2. Trong repo: `git fetch && git switch {DEVELOP}`, commit .github/ vào {DEVELOP}"
          " (AGENTS.md và .omi/ ở workspace, không commit).\n"
          + ("" if from_template else "  3. Tạo views theo docs/views.md (hoặc dùng --from-template lần sau).\n"))
