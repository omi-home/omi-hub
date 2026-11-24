"""Use case init: bootstrap Issue Types, Project, fields; ghi template vào repo và workspace."""
import json
from pathlib import Path

from omi_hub.config import load_pr_template, load_templates
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


def init(wf, milestone=None, from_template=None, template_only=False, hub_repo="omi-home/omi-hub",
             test_cmd=None, lint_cmd=None, accept_cmd=None, repo_dir_="."):
    """Chạy từ thư mục workspace; repo_dir_ = đường dẫn repo git tương đối với workspace."""
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
    old = json.loads(CONFIG.read_text(encoding="utf-8")) if CONFIG.exists() else {}
    new_cmds = {"test": test_cmd, "lint": lint_cmd, "accept": accept_cmd}
    cfg = {"owner": owner, "repo": repo, "repo_dir": repo_dir_, "project_number": number,
           "project_id": gh.project_node_id(owner, number), "fields": gh.load_fields(owner, number),
           "commands": {**old.get("commands", {}), **{k: v for k, v in new_cmds.items() if v}},
           "security_paths": old.get("security_paths", DEFAULT_SECURITY),
           "review_max_diff_lines": old.get("review_max_diff_lines", 1500),
           "default_branch": gh.default_branch(owner, repo)}
    CONFIG.parent.mkdir(exist_ok=True)
    CONFIG.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_templates(hub_repo, Path(repo_dir_), Path("."))
    gh.set_variable(cfg, "OMI_CONFIG", json.dumps(cfg, ensure_ascii=False))  # Action không có .omi/ của workspace
    gh.ensure_label(cfg, "security")  # label bật security review (spec 5.6)
    if milestone:
        gh.ensure_milestone(cfg, milestone)
    print(f"✅ Project #{number} đã gắn với {owner}/{repo}.\n"
          "Việc còn lại cho người:\n"
          "  1. Tạo secret OMI_PROJECT_TOKEN (fine-grained PAT: org Projects RW; repo Issues RW, Pull requests R;"
          f" Contents R cho {hub_repo}).\n"
          "  2. Commit .github/ trong repo (AGENTS.md và .omi/ ở workspace, không commit).\n"
          + ("" if from_template else "  3. Tạo views theo docs/views.md (hoặc dùng --from-template lần sau).\n"))
