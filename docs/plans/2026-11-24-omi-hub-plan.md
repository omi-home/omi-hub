# omi-hub Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Plugin Claude Code `omi-hub` bootstrap và vận hành quy trình dự án chuẩn (cây Epic → Story/Functional Requirement/Non-Functional Requirement/Change Request → Task, Bug) trên GitHub Projects, có lifecycle theo loại, rework, rollup, audit.

**Architecture:** Plugin gồm skills + hooks + 2 subagent + một CLI Python stdlib (`scripts/omi.py`). Core là package `scripts/omi_hub/` theo clean architecture (phụ thuộc chỉ đi vào trong): `domain/` (luật thuần, không I/O, test đầy đủ), `config/` (`workflow.json`, templates + hàm nạp), `infrastructure/` (nơi duy nhất gọi `gh` CLI), `application/` (use case điều phối), `cli/` (argparse, output); `scripts/omi.py` chỉ là entrypoint mỏng. Luật khai báo trong `config/workflow.json`.

> **Ánh xạ tên trong plan (đổi từ Task 002):** code mẫu các task sau viết theo bố cục phẳng cũ — khi làm, đặt vào module tương ứng, mỗi module một trách nhiệm:
> - `rules.load_workflow`, `rules.load_templates`, `workflow.json`, `templates.json`, `pr_template.json` → `omi_hub.config`
> - `rules.sections/prefix/with_prefix/check_template/check_pr/fill/skeleton` → `omi_hub.domain.templates`
- `rules.RuleError` → `omi_hub.domain.errors`; transition/Blocked/`BLOCKED`/`is_terminal`/`needs_human` → `omi_hub.domain.lifecycle`
> - rework → `domain/rework.py`; quan hệ cha–con, rollup → `domain/relations.py`; guards → `domain/guards.py`; invariants → `domain/audit.py`; chọn next → `domain/planning.py` (cùng `validate_plan`)
> - `gh.*` → `omi_hub/infrastructure/github/`: `client` (`GhError`, `run`, `graphql`, `rest`, `repo_path`=`_r`, `repo_full`=`_repo`), `nodes` (helper đọc node GraphQL), `issues` (snapshot, thao tác issue, comment, audit issue, `AUDIT_TITLE`), `project` (`FIELD_KINDS`, items, field, add item), `milestones`, `bootstrap` (Issue Types, project, fields, label, variable); test mock `client.graphql`/`client.run`; lệnh trong `omi.py` → `omi_hub/application/<nhóm lệnh>.py` (bỏ tiền tố `cmd_`, dùng `from omi_hub.infrastructure.github import gateway as gh`, test thay `<module>.gh` bằng bản giả) + đăng ký subcommand trong `omi_hub/cli/main.py` (`build_parser`, `run`); đã có: `application/workspace` (`find_root`, `load_cfg`, `repo_dir`, `tmp_dir(cfg)` thay global `TMP`), `application/items` (`snapshot`, `apply_status`, `rollup_up`, `new_item`, `move`, `rework`, `block`, `unblock`), `application/views` (`tree` trả dòng, `next_item`); `application/setup` (`init`, `write_templates`, `CONFIG`, `TEMPLATES`, `DEFAULT_SECURITY`); `domain/forms` (`render_form`, `form_filename`, `render_pr_template`); `scripts/omi.py` chỉ là entrypoint; helper text thuần → `omi_hub/domain/text.py`
> - Test: `tests/test_<layer>_<module>.py`, import `from omi_hub.<layer> import <module>`. GitHub Action chạy `omi.py audit` để kiểm tra bất biến khi người sửa tay trên web.

**Tech Stack:** Python ≥ 3.11 stdlib (`json`, `re`, `subprocess`, `argparse`, `unittest`), `gh` CLI ≥ 2.60, GitHub REST + GraphQL (Issue Types, sub-issues, issue dependencies, Projects v2), Claude Code plugin (skills, hooks, agents).

**Spec:** [docs/specs/2026-11-24-omi-hub-design.md](../specs/2026-11-24-omi-hub-design.md) — đọc trước khi làm bất kỳ task nào.

## Global Constraints

- Python chỉ dùng stdlib, tương thích Python 3.11+. Không thêm dependency.
- Mọi lời gọi GitHub đi qua `scripts/gh.py`; `rules.py` không I/O ngoài đọc `workflow.json`.
- Thông điệp cho người dùng/agent viết tiếng Việt; tên status/type/field giữ tiếng Anh đúng như spec.
- 7 Issue Types: `Epic`, `User Story`, `Functional Requirement`, `Non-Functional Requirement`, `Change Request`, `Task`, `Bug`.
- 10 Status theo đúng thứ tự: `Draft, Triage, Approved, Ready, In Progress, In Review, In QA, Blocked, Done, Cancelled`.
- Field Project: `Status`, `Priority` (P0–P3), `Estimate` (number), `Rework Count` (number), `Blocked Reason` (text).
- `max_rework` = 3. Approved luôn cần người xác nhận (hook `ask`).
- Chỉ `AGENTS.md`, không tạo `CLAUDE.md`. Memory subagent: `memory: project`.
- **Mô hình workspace (spec D12):** `AGENTS.md`, `.claude/`, `.omi/` nằm ở thư mục workspace; repo git là thư mục con (`repo_dir` trong `.omi/project.json`). Không ghi file agent/omi vào repo; repo chỉ nhận `.github/` (issue forms, PR template, workflow). Mọi lệnh git/gh cần working copy chạy với `cwd = repo_dir`.
- Đọc/ghi file luôn `encoding="utf-8"` (chạy trên Windows).
- Chạy test từ thư mục `omi-hub/`: `python -m unittest discover -s tests -v`.
- Không xóa issue; không tự đóng milestone; không ghi đè body issue của người dùng (trừ khi tạo mới).
- **Tối ưu token (spec mục 2.1):** việc gì script làm được thì không dùng LLM. Output CLI một dòng có tiền tố (`START`, `CHECK PASS|FAIL`, `REVIEW`, `QA FAIL`, `DONE`, `ACCEPT PASS|FAIL`); log dài ghi vào `.omi/tmp/`, chỉ in đường dẫn. Skill/agent/AGENTS.md viết ngắn nhất có thể.

## File Structure

| File | Trách nhiệm |
|---|---|
| `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` | Manifest plugin + marketplace để cài |
| `scripts/omi_hub/config/` | `workflow.json` (types, statuses, transitions, parents, requires, rollup), templates JSON, hàm nạp |
| `scripts/omi_hub/domain/` | Luật thuần: `errors`, `lifecycle` (transition, blocked), `rework`, `relations` (quan hệ, rollup), `guards`, `audit`, `planning` (next, validate plan), `text` |
| `scripts/omi_hub/infrastructure/github/` | Gọi `gh`: GraphQL/REST, snapshot issue, project items, ghi field, tạo issue, bootstrap |
| `scripts/omi_hub/application/`, `scripts/omi_hub/cli/`, `scripts/omi.py` (entrypoint) | CLI: init, new, move, rework, block, unblock, tree, next, apply, plan-show, audit, context, start, check, submit, review-done, qa, accept, impact, status, resume, template, pr-lint; helper text thuần |
| `hooks/hooks.json`, `hooks/guard.py` | PreToolUse chặn đi tắt / hỏi khi Approved; SessionStart in `OMI_CLI` (1 dòng) |
| `skills/omi-{plan,implement,change}/SKILL.md` | 3 việc cần LLM: phân rã PRD, vòng implement, Change Request/Bug |
| `skills/omi-{status,resume}/SKILL.md` | Lớp mỏng gọi `status` / `resume` (logic nằm trong CLI) |
| `agents/omi-reviewer.md`, `agents/omi-security-reviewer.md` | Code review / security review, mỗi task đúng 1 lượt (code do phiên chính viết, không có subagent viết code) |
| `templates/AGENTS.md`, `templates/ISSUE_TEMPLATE/*.yml`, `templates/workflows/omi-audit.yml` | File ghi vào repo đích khi init |
| `docs/views.md` | Hướng dẫn tạo 5 view trong Project mẫu |
| `tests/test_*.py`, `tests/e2e.sh` | Unit test + kịch bản e2e sandbox |

---

## Phase 0 — Spike

### Task 001: Xác minh API GitHub và cơ chế plugin

Mục tiêu: xác nhận các giả định ở spec mục 9 trước khi viết code.

> **Đã xác minh khi khởi tạo omi-hub (2026-11-24, Project #8):** tạo Issue Type tên dài có dấu cách ✓; tạo issue với `type` qua REST ✓; `POST sub_issues` ✓; `updateProjectV2Field` đặt 10 option Status cho Project rỗng ✓; `gh project field-list` **không** trả field Type (mục 6 — kiểm trên UI); gắn sub-issue cho item đã có trong Project → GitHub **tự thêm** vào Project (bất đồng bộ), `addProjectV2ItemById` lỗi `Content already exists` (xử lý ở Task 007 `add_to_project`). Các bước dưới vẫn chạy đủ trên sandbox để ghi kết quả. Kết quả là `docs/spike-results.md`; mọi lệnh ở đây là thử nghiệm, không giữ lại code.

**Files:**
- Create: `docs/spike-results.md`

- [ ] **Step 1: Xin người dùng xác nhận tạo repo sandbox** `omi-home/omi-sandbox` (private) và một Project thử. Không làm bước tiếp nếu chưa được đồng ý.

- [ ] **Step 2: Tạo sandbox**

```bash
gh repo create omi-home/omi-sandbox --private --add-readme
O=omi-home; R=omi-home/omi-sandbox
```

- [ ] **Step 3: Issue Types (tiên quyết, kèm tên dài có dấu cách)**

```bash
gh api orgs/$O/issue-types --jq '.[].name'
gh api -X POST orgs/$O/issue-types -f name="Spike Non-Functional Requirement" -F is_enabled=true --jq '.id'
# ghi lại id rồi xóa:
gh api -X DELETE orgs/$O/issue-types/<ID>
```
Expected: list trả về tên types; POST trả id.

- [ ] **Step 4: Tạo issue có type bằng REST, sub-issue, dependency**

```bash
P=$(gh api -X POST repos/$R/issues -f title="spike parent" -f type=Task --jq '.number')
C=$(gh api -X POST repos/$R/issues -f title="spike child" -f type=Task --jq '.number')
CID=$(gh api repos/$R/issues/$C --jq '.id')
PID=$(gh api repos/$R/issues/$P --jq '.id')
gh api -X POST repos/$R/issues/$P/sub_issues -F sub_issue_id=$CID
gh api -X POST repos/$R/issues/$C/dependencies/blocked_by -F issue_id=$PID
```
Expected: tất cả trả 201.

- [ ] **Step 5: Truy vấn snapshot GraphQL đúng như `gh.SNAPSHOT_QUERY` (Task 007)**

Chạy query trong Task 007 Step 3 với `number=$C`. Expected: có `issueType.name`, `parent.number = $P`, `blockedBy.nodes[0].state = OPEN`, `subIssues` của `$P` chứa `$C`. Nếu field nào lỗi tên → ghi tên đúng vào spike-results và sửa query trong Task 007.

- [ ] **Step 6: Project: tạo, field-list, cột Type, đổi options Status**

```bash
N=$(gh project create --owner $O --title "omi spike" --format json --jq '.number')
gh project field-list $N --owner $O --format json
```
Ghi lại: có field tên `Type` (issue type) không; JSON của field single-select có khóa `options` với `id`,`name` không. Sau đó chạy mutation `UPDATE_STATUS` (Task 008) với id field Status và 10 status. Expected: `gh project field-list` hiện đủ 10 options đúng thứ tự.

- [ ] **Step 7: `gh project copy` có giữ views + workflows**

Trong UI tạo 1 view "Board" ở project `omi spike`, bật workflow "Auto-add" → `gh project copy $N --source-owner $O --target-owner $O --title "omi spike copy" --format json`. Mở bản copy trên web, ghi lại view/workflow nào được giữ.

- [ ] **Step 8: Phân trang và issue forms, Action trigger**

```bash
gh api --paginate --slurp "repos/$R/issues/$P/comments?per_page=100"
```
Expected: mảng các trang (`[[...]]`). Commit vào sandbox file `.github/ISSUE_TEMPLATE/task.yml` (Task 011) và workflow:

```yaml
name: spike
on: {issues: {types: [typed]}}
jobs: {t: {runs-on: ubuntu-latest, steps: [{run: echo typed}]}}
```
Mở issue từ form trên web → kiểm tra issue có type Task; đổi type một issue → kiểm tra workflow chạy.

- [ ] **Step 9: Cơ chế plugin**

Tạo plugin tối thiểu tạm trong scratchpad: `hooks/hooks.json` SessionStart chạy `python -c "import os;print('ROOT='+os.environ.get('CLAUDE_PLUGIN_ROOT','MISSING'))"` và `agents/probe.md` có `memory: project`. Chạy `claude --plugin-dir <thư mục>` trong sandbox clone, gọi agent probe yêu cầu nó ghi 1 dòng vào memory. Ghi lại: `ROOT=` có giá trị; thư mục `.claude/agent-memory/probe-probe/` có được tạo (plugin-agent).

- [ ] **Step 10: Ghi kết quả**

`docs/spike-results.md`:

```markdown
# Spike results (2026-11-24)
| # | Giả định | Kết quả | Quyết định |
|---|---|---|---|
| 1 | REST issue-types list/create | | |
| 2 | Tạo issue với `type` (REST) | | |
| 3 | sub_issues POST + GraphQL parent/subIssues | | |
| 4 | dependencies/blocked_by + GraphQL blockedBy | | |
| 5 | GraphQL closedByPullRequestsReferences | | |
| 6 | Project có cột Type | | |
| 7 | updateProjectV2Field options Status | | |
| 8 | project copy giữ views/workflows | | |
| 9 | --paginate --slurp | | |
| 10 | Issue form `type:` | | |
| 11 | Action `issues: typed` | | |
| 12 | CLAUDE_PLUGIN_ROOT trong hook | | |
| 13 | agent memory: project trong plugin | | |
| 14 | Issue Type tên dài có dấu cách/gạch ngang ("Non-Functional Requirement") tạo + gán + filter `type:"..."` được | | |
| 15 | Fine-grained PAT (`OMI_PROJECT_TOKEN`) đọc/ghi được Project v2 của org | | |
```
Nếu mục 1–4 thất bại: dừng, báo người dùng, cập nhật spec. Các mục khác: áp dụng phương án dự phòng ở spec mục 9 và sửa task tương ứng trước khi làm.

- [ ] **Step 11: Dọn dẹp** project spike (`gh project delete N --owner $O`), giữ repo sandbox cho e2e.

---

## Phase 1 — Luật thuần (`rules.py`)

### Task 002: Khung plugin, `workflow.json`, transitions và Blocked

**Files:**
- Create: `scripts/omi_hub/__init__.py`, `scripts/omi_hub/config/{__init__.py,workflow.json}`, `scripts/omi_hub/domain/{__init__.py,errors.py,lifecycle.py}`, `tests/test_domain_lifecycle.py`

**Interfaces:**
- Produces: `omi_hub.config.load_workflow(path=WORKFLOW_PATH) -> dict`; `omi_hub.domain.errors.RuleError(errors: str|list[str])` có `.errors: list[str]`; `omi_hub.domain.lifecycle`: `BLOCKED = "Blocked"`, `allowed_statuses(wf, type_) -> set[str]`, `is_terminal(wf, status) -> bool`, `needs_human(wf, target) -> bool`, `transition(wf, type_, current, target, blocked_from=None) -> list[str]` (tên guard).
- Đã làm (2026-11-24): code đặt theo layer (xem "Ánh xạ tên" ở đầu plan); nội dung code mẫu dưới đây giữ nguyên.

- [ ] **Step 1: Khởi tạo git cho `omi-hub/`** (xác nhận với người dùng trước nếu chưa có repo)

```bash
cd omi-hub && git init
printf '__pycache__/\n*.pyc\n' > .gitignore
```

- [ ] **Step 2: Viết `scripts/workflow.json`**

```json
{
  "max_rework": 3,
  "statuses": ["Draft", "Triage", "Approved", "Ready", "In Progress", "In Review", "In QA", "Blocked", "Done", "Cancelled"],
  "terminal": ["Done", "Cancelled"],
  "human_approval": ["Approved"],
  "priorities": ["P0", "P1", "P2", "P3"],
  "types": {
    "Epic": {
      "initial": "Draft", "parents": [], "requires": ["milestone"], "on_children_done": "Done",
      "transitions": [
        {"from": "Draft", "to": "Approved"},
        {"from": "Approved", "to": "In Progress"},
        {"from": "In Progress", "to": "Done", "guards": ["children_terminal"]},
        {"from": ["Draft", "Approved"], "to": "Cancelled", "guards": ["reason"]},
        {"from": "In Progress", "to": "Cancelled", "guards": ["reason", "children_terminal"]}
      ]
    },
    "User Story": {
      "initial": "Draft", "parents": ["Epic"], "requires": ["parent"], "on_children_done": "In QA",
      "transitions": [
        {"from": "Draft", "to": "Approved"},
        {"from": "Approved", "to": "In Progress"},
        {"from": "In Progress", "to": "In QA", "guards": ["children_terminal"]},
        {"from": "In QA", "to": "Done"},
        {"from": ["Draft", "Approved"], "to": "Cancelled", "guards": ["reason"]}
      ]
    },
    "Functional Requirement": {
      "initial": "Draft", "parents": ["Epic", "User Story"], "requires": ["parent"], "on_children_done": "In QA",
      "transitions": [
        {"from": "Draft", "to": "Approved"},
        {"from": "Approved", "to": "In Progress"},
        {"from": "In Progress", "to": "In QA", "guards": ["children_terminal"]},
        {"from": "In QA", "to": "Done"},
        {"from": ["Draft", "Approved"], "to": "Cancelled", "guards": ["reason"]}
      ]
    },
    "Non-Functional Requirement": {
      "initial": "Draft", "parents": ["Epic", "User Story", "Functional Requirement"], "requires": ["parent"], "on_children_done": "In QA",
      "transitions": [
        {"from": "Draft", "to": "Approved"},
        {"from": "Approved", "to": "In Progress"},
        {"from": "In Progress", "to": "In QA", "guards": ["children_terminal"]},
        {"from": "In QA", "to": "Done"},
        {"from": ["Draft", "Approved"], "to": "Cancelled", "guards": ["reason"]}
      ]
    },
    "Change Request": {
      "initial": "Triage", "parents": ["Epic"], "requires": ["parent", "affects"], "on_children_done": "Done",
      "transitions": [
        {"from": "Triage", "to": "Approved", "guards": ["impact_analysis"]},
        {"from": "Triage", "to": "Cancelled", "guards": ["reason"]},
        {"from": "Approved", "to": "In Progress"},
        {"from": "In Progress", "to": "Done", "guards": ["children_terminal"]}
      ]
    },
    "Task": {
      "initial": "Draft", "parents": ["User Story", "Functional Requirement", "Non-Functional Requirement", "Change Request"], "requires": ["parent"],
      "transitions": [
        {"from": "Draft", "to": "Ready", "guards": ["parent_ready"]},
        {"from": "Ready", "to": "In Progress", "guards": ["no_open_blockers"]},
        {"from": "In Progress", "to": "In Review", "guards": ["pr_open"]},
        {"from": "In Review", "to": "In QA"},
        {"from": "In QA", "to": "Done", "guards": ["pr_merged"]},
        {"from": ["Draft", "Ready", "In Progress"], "to": "Cancelled", "guards": ["reason"]}
      ]
    },
    "Bug": {
      "initial": "Triage", "parents": [], "requires": ["affects", "milestone"],
      "transitions": [
        {"from": "Triage", "to": "Ready"},
        {"from": "Triage", "to": "Cancelled", "guards": ["reason"]},
        {"from": "Ready", "to": "In Progress", "guards": ["no_open_blockers"]},
        {"from": "In Progress", "to": "In Review", "guards": ["pr_open"]},
        {"from": "In Review", "to": "In QA"},
        {"from": "In QA", "to": "Done", "guards": ["pr_merged"]},
        {"from": ["Ready", "In Progress"], "to": "Cancelled", "guards": ["reason"]}
      ]
    }
  }
}
```

- [ ] **Step 3: Viết test thất bại `tests/test_rules.py`**

```python
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import rules  # noqa: E402
from rules import RuleError  # noqa: E402

WF = rules.load_workflow()


class TestWorkflowFile(unittest.TestCase):
    def test_every_status_used_is_declared(self):
        for t in WF["types"]:
            self.assertLessEqual(rules.allowed_statuses(WF, t), set(WF["statuses"]), t)

    def test_status_sets_per_type(self):
        self.assertEqual(rules.allowed_statuses(WF, "Epic"),
                         {"Draft", "Approved", "In Progress", "Blocked", "Done", "Cancelled"})
        self.assertEqual(rules.allowed_statuses(WF, "User Story"),
                         {"Draft", "Approved", "In Progress", "In QA", "Blocked", "Done", "Cancelled"})
        self.assertEqual(rules.allowed_statuses(WF, "Change Request"),
                         {"Triage", "Approved", "In Progress", "Blocked", "Done", "Cancelled"})
        self.assertEqual(rules.allowed_statuses(WF, "Task"),
                         {"Draft", "Ready", "In Progress", "In Review", "In QA", "Blocked", "Done", "Cancelled"})
        self.assertEqual(rules.allowed_statuses(WF, "Bug"),
                         {"Triage", "Ready", "In Progress", "In Review", "In QA", "Blocked", "Done", "Cancelled"})


class TestTransition(unittest.TestCase):
    def test_task_happy_path_guards(self):
        self.assertEqual(rules.transition(WF, "Task", "Draft", "Ready"), ["parent_ready"])
        self.assertEqual(rules.transition(WF, "Task", "Ready", "In Progress"), ["no_open_blockers"])
        self.assertEqual(rules.transition(WF, "Task", "In Progress", "In Review"), ["pr_open"])
        self.assertEqual(rules.transition(WF, "Task", "In Review", "In QA"), [])
        self.assertEqual(rules.transition(WF, "Task", "In QA", "Done"), ["pr_merged"])

    def test_skip_step_rejected(self):
        with self.assertRaisesRegex(RuleError, "không được chuyển"):
            rules.transition(WF, "Task", "Ready", "Done")

    def test_status_not_used_by_type(self):
        with self.assertRaisesRegex(RuleError, "không dùng"):
            rules.transition(WF, "Task", "Draft", "Approved")

    def test_terminal_is_final(self):
        with self.assertRaisesRegex(RuleError, "kết thúc"):
            rules.transition(WF, "User Story", "Done", "In Progress")

    def test_same_status_rejected(self):
        with self.assertRaisesRegex(RuleError, "đã ở"):
            rules.transition(WF, "Task", "Ready", "Ready")

    def test_no_approved_back_to_draft(self):
        with self.assertRaises(RuleError):
            rules.transition(WF, "Functional Requirement", "Approved", "Draft")

    def test_unknown_type(self):
        with self.assertRaisesRegex(RuleError, "không thuộc workflow"):
            rules.transition(WF, "Feature", "Draft", "Ready")

    def test_cr_approve_needs_impact(self):
        self.assertEqual(rules.transition(WF, "Change Request", "Triage", "Approved"), ["impact_analysis"])

    def test_needs_human(self):
        self.assertTrue(rules.needs_human(WF, "Approved"))
        self.assertFalse(rules.needs_human(WF, "Done"))


class TestBlocked(unittest.TestCase):
    def test_block_from_any_open_status(self):
        for st in ["Draft", "Ready", "In Progress", "In Review", "In QA"]:
            self.assertEqual(rules.transition(WF, "Task", st, "Blocked"), ["blocker_present"])

    def test_cannot_block_terminal(self):
        with self.assertRaisesRegex(RuleError, "kết thúc"):
            rules.transition(WF, "Task", "Done", "Blocked")

    def test_unblock_only_to_previous(self):
        self.assertEqual(rules.transition(WF, "Task", "Blocked", "Ready", blocked_from="Ready"),
                         ["no_open_blockers"])
        with self.assertRaisesRegex(RuleError, "trước khi block"):
            rules.transition(WF, "Task", "Blocked", "In Progress", blocked_from="Ready")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 4: Chạy để thấy thất bại**

Run: `python -m unittest discover -s tests -v`
Expected: lỗi `ModuleNotFoundError: No module named 'rules'`.

- [ ] **Step 5: Viết `scripts/rules.py`**

```python
"""Luật workflow omi-hub. Thuần: không I/O ngoài đọc workflow.json."""
import json
import re
from pathlib import Path

WORKFLOW_PATH = Path(__file__).with_name("workflow.json")
BLOCKED = "Blocked"


class RuleError(Exception):
    def __init__(self, errors):
        self.errors = [errors] if isinstance(errors, str) else list(errors)
        super().__init__("; ".join(self.errors))


def load_workflow(path=WORKFLOW_PATH):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _as_list(v):
    return v if isinstance(v, list) else [v]


def _type(wf, type_):
    try:
        return wf["types"][type_]
    except KeyError:
        raise RuleError(f"Loại '{type_}' không thuộc workflow omi") from None


def allowed_statuses(wf, type_):
    t = _type(wf, type_)
    out = {t["initial"], BLOCKED}
    for tr in t["transitions"]:
        out.update(_as_list(tr["from"]))
        out.add(tr["to"])
    return out


def is_terminal(wf, status):
    return status in wf["terminal"]


def needs_human(wf, target):
    return target in wf["human_approval"]


def transition(wf, type_, current, target, blocked_from=None):
    """Trả danh sách guard cần kiểm cho current -> target; RuleError nếu không hợp lệ."""
    if target not in allowed_statuses(wf, type_):
        raise RuleError(f"{type_} không dùng status '{target}'")
    if current == target:
        raise RuleError(f"Item đã ở '{target}'")
    if is_terminal(wf, current):
        raise RuleError(f"'{current}' là trạng thái kết thúc, không chuyển tiếp được")
    if target == BLOCKED:
        return ["blocker_present"]
    if current == BLOCKED:
        if target != blocked_from:
            raise RuleError(f"Unblock chỉ được về trạng thái trước khi block ('{blocked_from}')")
        return ["no_open_blockers"]
    for tr in _type(wf, type_)["transitions"]:
        if current in _as_list(tr["from"]) and tr["to"] == target:
            return list(tr.get("guards", []))
    raise RuleError(f"{type_}: không được chuyển '{current}' → '{target}'")
```

- [ ] **Step 6: Chạy test**

Run: `python -m unittest discover -s tests -v`
Expected: tất cả PASS.

- [ ] **Step 7: Commit**

```bash
git add .gitignore scripts/workflow.json scripts/rules.py tests/test_rules.py
git commit -m "feat(rules): workflow.json và luật transition/blocked"
```

### Task 003: Rework, quan hệ cha–con, rollup

**Files:**
- Modify: `scripts/rules.py` (thêm cuối file)
- Test: `tests/test_rules.py` (thêm class)

**Interfaces:**
- Consumes: Task 002.
- Produces: `rules.REWORK_FROM = ("In Review", "In QA")`, `rules.rework(wf, type_, current, count) -> tuple[str, int]`, `rules.check_parent(wf, child_type, parent_type: str|None) -> None` (raise RuleError), `rules.check_links(wf, type_, affects_count: int, has_milestone: bool) -> None`, `rules.rollup(wf, parent_type, parent_status, child_statuses: list[str], trigger: str) -> str|None`.

- [ ] **Step 1: Thêm test**

```python
class TestRework(unittest.TestCase):
    def test_from_review(self):
        self.assertEqual(rules.rework(WF, "Task", "In Review", 0), ("In Progress", 1))

    def test_story_from_qa(self):
        self.assertEqual(rules.rework(WF, "User Story", "In QA", 1), ("In Progress", 2))

    def test_limit_blocks(self):
        self.assertEqual(rules.rework(WF, "Task", "In QA", 3), ("Blocked", 4))

    def test_invalid_source(self):
        with self.assertRaisesRegex(RuleError, "Rework"):
            rules.rework(WF, "Task", "In Progress", 0)

    def test_type_without_qa(self):
        with self.assertRaises(RuleError):
            rules.rework(WF, "Epic", "In QA", 0)


class TestRelations(unittest.TestCase):
    def test_valid_parents(self):
        rules.check_parent(WF, "Task", "Functional Requirement")
        rules.check_parent(WF, "Non-Functional Requirement", "User Story")
        rules.check_parent(WF, "Epic", None)
        rules.check_parent(WF, "Bug", None)

    def test_wrong_parent(self):
        with self.assertRaisesRegex(RuleError, "không được làm con"):
            rules.check_parent(WF, "Task", "Epic")
        with self.assertRaisesRegex(RuleError, "không được làm con"):
            rules.check_parent(WF, "Epic", "Epic")

    def test_missing_required_parent(self):
        with self.assertRaisesRegex(RuleError, "bắt buộc có parent"):
            rules.check_parent(WF, "Task", None)

    def test_links(self):
        rules.check_links(WF, "Task", 0, False)
        with self.assertRaisesRegex(RuleError, "Affects"):
            rules.check_links(WF, "Change Request", 0, True)
        with self.assertRaisesRegex(RuleError, "milestone"):
            rules.check_links(WF, "Bug", 1, False)
        with self.assertRaisesRegex(RuleError, "milestone"):
            rules.check_links(WF, "Epic", 0, False)


class TestRollup(unittest.TestCase):
    def test_first_child_starts_parent(self):
        self.assertEqual(rules.rollup(WF, "User Story", "Approved", ["In Progress", "Ready"], "In Progress"),
                         "In Progress")

    def test_draft_parent_not_started(self):
        self.assertIsNone(rules.rollup(WF, "User Story", "Draft", ["In Progress"], "In Progress"))

    def test_all_children_done_story_to_qa(self):
        self.assertEqual(rules.rollup(WF, "Functional Requirement", "In Progress", ["Done", "Cancelled"], "Done"), "In QA")

    def test_partial_children(self):
        self.assertIsNone(rules.rollup(WF, "User Story", "In Progress", ["Done", "In Review"], "Done"))

    def test_epic_and_cr_to_done(self):
        self.assertEqual(rules.rollup(WF, "Epic", "In Progress", ["Done", "Cancelled"], "Done"), "Done")
        self.assertEqual(rules.rollup(WF, "Change Request", "In Progress", ["Done"], "Done"), "Done")

    def test_all_cancelled_needs_human(self):
        self.assertIsNone(rules.rollup(WF, "Epic", "In Progress", ["Cancelled"], "Cancelled"))
```

- [ ] **Step 2: Chạy để thấy thất bại**

Run: `python -m unittest discover -s tests -v`
Expected: FAIL `AttributeError: module 'rules' has no attribute 'rework'`.

- [ ] **Step 3: Thêm vào `scripts/rules.py`**

```python
REWORK_FROM = ("In Review", "In QA")


def rework(wf, type_, current, count):
    """Review/QA fail: trả (status mới, rework count mới). Vượt max_rework -> Blocked."""
    if current not in REWORK_FROM or current not in allowed_statuses(wf, type_):
        raise RuleError(f"Rework chỉ áp dụng từ In Review/In QA (hiện tại: '{current}')")
    count += 1
    return (BLOCKED if count > wf["max_rework"] else "In Progress"), count


def check_parent(wf, child_type, parent_type):
    t = _type(wf, child_type)
    if parent_type is None:
        if "parent" in t["requires"]:
            raise RuleError(f"{child_type} bắt buộc có parent ({', '.join(t['parents'])})")
        return
    if parent_type not in t["parents"]:
        allowed = ", ".join(t["parents"]) or "không có"
        raise RuleError(f"{child_type} không được làm con của {parent_type} (cho phép: {allowed})")


def check_links(wf, type_, affects_count, has_milestone):
    req = _type(wf, type_)["requires"]
    errs = []
    if "affects" in req and affects_count == 0:
        errs.append(f"{type_} cần ít nhất 1 item Affects (--affects)")
    if "milestone" in req and not has_milestone:
        errs.append(f"{type_} cần milestone (--milestone)")
    if errs:
        raise RuleError(errs)


def rollup(wf, parent_type, parent_status, child_statuses, trigger):
    """Status mới của parent sau khi một con đổi sang `trigger`, hoặc None."""
    if trigger == "In Progress" and parent_status == "Approved":
        return "In Progress"
    target = _type(wf, parent_type).get("on_children_done")
    if (target and parent_status == "In Progress" and child_statuses
            and all(is_terminal(wf, s) for s in child_statuses)):
        if target == "Done" and "Done" not in child_statuses:
            return None  # mọi con bị hủy: để người quyết
        return target
    return None
```

- [ ] **Step 4: Chạy test** — Run: `python -m unittest discover -s tests -v` — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/rules.py tests/test_rules.py
git commit -m "feat(rules): rework, quan hệ cha-con, rollup"
```

### Task 004: Guards

**Files:**
- Modify: `scripts/rules.py`
- Test: `tests/test_rules.py`

**Interfaces:**
- Consumes: Task 002.
- Produces: `rules.evaluate_guards(guards: list[str], snap: dict, reason: str|None=None) -> list[str]` (thông điệp lỗi). `snap` là snapshot do `gh.issue_snapshot` trả (Task 007) với các khóa dùng ở đây: `parent: {"number","type","status"}|None`, `children: [{"status",...}]`, `open_blockers: int`, `prs: [{"state","merged"}]`, tùy chọn `has_impact: bool`.

- [ ] **Step 1: Thêm test**

```python
def snap(**kw):
    base = {"number": 1, "type": "Task", "status": "Draft", "parent": None,
            "children": [], "open_blockers": 0, "prs": []}
    base.update(kw)
    return base


class TestGuards(unittest.TestCase):
    def ev(self, g, s, reason=None):
        return rules.evaluate_guards([g], s, reason)

    def test_reason(self):
        self.assertEqual(len(self.ev("reason", snap())), 1)
        self.assertEqual(len(self.ev("reason", snap(), "   ")), 1)
        self.assertEqual(self.ev("reason", snap(), "trùng #3"), [])

    def test_parent_ready(self):
        self.assertTrue(self.ev("parent_ready", snap()))
        self.assertTrue(self.ev("parent_ready", snap(parent={"number": 2, "type": "Functional Requirement", "status": "Draft"})))
        self.assertEqual(self.ev("parent_ready", snap(parent={"number": 2, "type": "Functional Requirement", "status": "Approved"})), [])
        self.assertEqual(self.ev("parent_ready", snap(parent={"number": 2, "type": "Functional Requirement", "status": "In Progress"})), [])

    def test_blockers(self):
        self.assertTrue(self.ev("no_open_blockers", snap(open_blockers=2)))
        self.assertEqual(self.ev("no_open_blockers", snap()), [])

    def test_prs(self):
        self.assertTrue(self.ev("pr_open", snap()))
        self.assertEqual(self.ev("pr_open", snap(prs=[{"number": 9, "state": "OPEN", "merged": False}])), [])
        self.assertTrue(self.ev("pr_merged", snap(prs=[{"number": 9, "state": "OPEN", "merged": False}])))
        self.assertEqual(self.ev("pr_merged", snap(prs=[{"number": 9, "state": "MERGED", "merged": True}])), [])

    def test_children_terminal(self):
        self.assertTrue(self.ev("children_terminal", snap(children=[{"status": "Done"}, {"status": "Ready"}])))
        self.assertEqual(self.ev("children_terminal", snap(children=[{"status": "Done"}, {"status": "Cancelled"}])), [])

    def test_impact(self):
        self.assertTrue(self.ev("impact_analysis", snap()))
        self.assertEqual(self.ev("impact_analysis", snap(has_impact=True)), [])

    def test_blocker_present(self):
        self.assertTrue(self.ev("blocker_present", snap()))
        self.assertEqual(self.ev("blocker_present", snap(), "chờ API key"), [])
        self.assertEqual(self.ev("blocker_present", snap(open_blockers=1)), [])

    def test_unknown_guard_is_error(self):
        with self.assertRaises(KeyError):
            rules.evaluate_guards(["nope"], snap())
```

- [ ] **Step 2: Chạy để thấy thất bại** — Expected: `AttributeError: ... 'evaluate_guards'`.

- [ ] **Step 3: Thêm vào `scripts/rules.py`**

```python
def _has_reason(r):
    return bool(r and r.strip())


GUARDS = {
    "reason": lambda s, r: (_has_reason(r), "Cần --reason"),
    "parent_ready": lambda s, r: (
        bool(s["parent"]) and s["parent"]["status"] in ("Approved", "In Progress"),
        "Parent phải ở Approved hoặc In Progress"),
    "no_open_blockers": lambda s, r: (
        s["open_blockers"] == 0, f"Còn {s['open_blockers']} issue blocked-by đang mở"),
    "pr_open": lambda s, r: (
        any(p["state"] == "OPEN" for p in s["prs"]), "Cần PR đang mở có 'Closes #<số issue>'"),
    "pr_merged": lambda s, r: (any(p["merged"] for p in s["prs"]), "PR liên kết chưa merge"),
    "children_terminal": lambda s, r: (
        all(c["status"] in ("Done", "Cancelled") for c in s["children"]),
        "Còn item con chưa Done/Cancelled"),
    "impact_analysis": lambda s, r: (
        s.get("has_impact", False), "Change Request cần comment phân tích ảnh hưởng có <!-- omi:impact -->"),
    "blocker_present": lambda s, r: (
        _has_reason(r) or s["open_blockers"] > 0, "Cần --reason hoặc --by <issue chặn>"),
}


def evaluate_guards(guards, snap, reason=None):
    errs = []
    for g in guards:
        ok, msg = GUARDS[g](snap, reason)
        if not ok:
            errs.append(msg)
    return errs
```

- [ ] **Step 4: Chạy test** — Expected: PASS.
- [ ] **Step 5: Commit** — `git commit -am "feat(rules): guards"`

### Task 005: Audit invariants, chọn next, validate plan

**Files:**
- Modify: `scripts/rules.py`
- Test: `tests/test_rules.py`

**Interfaces:**
- Consumes: Task 002–003.
- Produces:
  - `rules.check_invariants(wf, item: dict, by_number: dict[int, dict]) -> list[dict]`; mỗi phần tử `{"number": int, "problem": str, "fix": tuple|None}`, fix ∈ `("add", status)`, `("status", status)`, `("close", "Done"|"Cancelled")`, `("milestone", title)`. `item` = project item chuẩn hóa (Task 007 `gh.normalize_project_item`): `number, title, id, type, status, state, state_reason, milestone, parent (int|None), blocked_reason, open_blockers, in_project, item_id`. Item ngoài Project chỉ cần `number, id, type, in_project=False`.
  - `rules.pick_next(wf, items: list[dict]) -> dict|None` (item thêm khóa `priority`, `milestone_due`).
  - `rules.validate_plan(wf, plan: dict) -> list[str]` (gồm kiểm key dạng `<chữ loại><NNN>`: `E001.S002.T003`), `rules.KEY_LETTER`.

- [ ] **Step 1: Thêm test**

```python
def item(**kw):
    base = {"number": 1, "title": "t", "id": "N1", "type": "Task", "status": "Ready", "state": "OPEN",
            "state_reason": None, "milestone": "v1", "parent": 10, "blocked_reason": None,
            "open_blockers": 0, "in_project": True, "item_id": "I1", "priority": None, "milestone_due": None}
    base.update(kw)
    return base


STORY = item(number=10, type="User Story", status="In Progress", parent=20)
EPIC = item(number=20, type="Epic", status="In Progress", parent=None)


def inv(it, *others):
    by = {i["number"]: i for i in (it, STORY, EPIC, *others)}
    return rules.check_invariants(WF, it, by)


class TestInvariants(unittest.TestCase):
    def test_clean(self):
        self.assertEqual(inv(item()), [])

    def test_untyped(self):
        self.assertEqual(len(inv(item(type=None))), 1)

    def test_not_in_project(self):
        self.assertEqual(inv({"number": 5, "id": "N5", "type": "Bug", "in_project": False})[0]["fix"],
                         ("add", "Triage"))

    def test_closed_but_open_status(self):
        self.assertEqual(inv(item(state="CLOSED", state_reason="COMPLETED"))[0]["fix"], ("status", "Done"))
        self.assertEqual(inv(item(state="CLOSED", state_reason="NOT_PLANNED"))[0]["fix"], ("status", "Cancelled"))

    def test_open_but_terminal(self):
        self.assertEqual(inv(item(status="Done"))[0]["fix"], ("close", "Done"))

    def test_status_not_valid_for_type(self):
        self.assertIn("không hợp lệ", inv(item(status="Approved"))[0]["problem"])

    def test_wrong_parent(self):
        self.assertEqual(len(inv(item(parent=20))), 1)

    def test_done_with_open_child(self):
        done_story = item(number=10, type="User Story", status="Done", state="CLOSED", parent=20)
        child = item(number=1, status="Ready")
        probs = rules.check_invariants(WF, done_story, {1: child, 10: done_story, 20: EPIC})
        self.assertIn("con chưa kết thúc", probs[0]["problem"])

    def test_blocked_without_reason(self):
        self.assertEqual(len(inv(item(status="Blocked"))), 1)
        self.assertEqual(inv(item(status="Blocked", blocked_reason="x")), [])

    def test_milestone_drift(self):
        self.assertEqual(inv(item(milestone="v2"))[0]["fix"], ("milestone", "v1"))

    def test_parent_outside_project_skipped(self):
        self.assertEqual(rules.check_invariants(WF, item(parent=99), {}), [])


class TestPickNext(unittest.TestCase):
    def test_priority_then_milestone_then_number(self):
        items = [item(number=3, priority="P2"), item(number=4, priority="P1"),
                 item(number=2, priority="P1", milestone_due="2026-12-01"),
                 item(number=5, priority="P0", open_blockers=1),
                 item(number=6, priority="P0", status="In Progress"),
                 item(number=7, priority="P0", type="User Story", status="Approved")]
        self.assertEqual(rules.pick_next(WF, items)["number"], 2)

    def test_none(self):
        self.assertIsNone(rules.pick_next(WF, [item(status="Draft")]))


AC = "Mô tả\n\n### Acceptance criteria\n- [ ] ok"


class TestValidatePlan(unittest.TestCase):
    def plan(self, items, **kw):
        return {"milestone": "v1", "items": items, **kw}

    def test_valid(self):
        p = self.plan([{"key": "E001", "type": "Epic", "title": "E", "children": [
            {"key": "E001.S001", "type": "User Story", "title": "S", "body": AC, "children": [
                {"key": "E001.S001.T001", "type": "Task", "title": "T"}]}]}])
        self.assertEqual(rules.validate_plan(WF, p), [])

    def test_errors(self):
        p = self.plan([{"key": "E001", "type": "Epic", "title": "E", "children": [
            {"key": "E001", "type": "User Story", "title": "S"},
            {"key": "E001.T001", "type": "Task", "title": "T"},
            {"key": "E001.C001", "type": "Change Request", "title": "C"}]}], milestone=None)
        errs = rules.validate_plan(WF, p)
        self.assertTrue(any("trùng" in e for e in errs))
        self.assertTrue(any("Acceptance criteria" in e for e in errs))
        self.assertTrue(any("không được làm con" in e for e in errs))
        self.assertTrue(any("Change Request" in e for e in errs))
        self.assertTrue(any("milestone" in e for e in errs))

    def test_key_format_nnn(self):
        bad = self.plan([{"key": "E1", "type": "Epic", "title": "E"}])
        self.assertTrue(any("key 'E1'" in e for e in rules.validate_plan(WF, bad)))
        wrong_letter = self.plan([{"key": "E001", "type": "Epic", "title": "E", "children": [
            {"key": "E001.T001", "type": "User Story", "title": "S", "body": AC}]}])
        self.assertTrue(any("key 'E001.T001'" in e for e in rules.validate_plan(WF, wrong_letter)))

    def test_child_of_existing_issue(self):
        p = self.plan([{"key": "T001", "type": "Task", "title": "T", "parent": 42}])
        self.assertEqual(rules.validate_plan(WF, p), [])
```

- [ ] **Step 2: Chạy để thấy thất bại** — Expected: `AttributeError ... 'check_invariants'`.

- [ ] **Step 3: Thêm vào `scripts/rules.py`**

```python
def check_invariants(wf, item, by_number):
    """Bất biến trên trạng thái hiện tại (dùng cho audit)."""
    out = []
    n, t = item["number"], item["type"]

    def bad(problem, fix=None):
        out.append({"number": n, "problem": problem, "fix": fix})

    if t not in wf["types"]:
        bad(f"chưa có Issue Type omi hợp lệ (hiện: {t})")
        return out
    if not item["in_project"]:
        bad("chưa có trong Project", ("add", wf["types"][t]["initial"]))
        return out
    st = item["status"]
    if st not in allowed_statuses(wf, t):
        bad(f"status '{st}' không hợp lệ cho {t}")
    parent = by_number.get(item["parent"]) if item["parent"] else None
    if parent or not item["parent"]:
        try:
            check_parent(wf, t, parent["type"] if parent else None)
        except RuleError as e:
            bad(str(e))
    closed = item["state"] == "CLOSED"
    if closed and not is_terminal(wf, st):
        bad(f"issue đã đóng nhưng Status là '{st}'",
            ("status", "Cancelled" if item["state_reason"] == "NOT_PLANNED" else "Done"))
    if not closed and is_terminal(wf, st):
        bad(f"Status '{st}' nhưng issue còn mở", ("close", st))
    if st == "Done" and any(c["parent"] == n and not is_terminal(wf, c["status"]) for c in by_number.values()):
        bad("Done nhưng còn con chưa kết thúc")
    if st == BLOCKED and not item["blocked_reason"] and item["open_blockers"] == 0:
        bad("Blocked nhưng không có Blocked Reason hay blocked-by")
    if parent and parent["milestone"] and item["milestone"] != parent["milestone"]:
        bad(f"milestone '{item['milestone']}' khác parent '{parent['milestone']}'", ("milestone", parent["milestone"]))
    return out


def pick_next(wf, items):
    """Task/Bug Ready, không bị chặn; ưu tiên Priority, rồi milestone đến hạn sớm, rồi số nhỏ."""
    order = {p: i for i, p in enumerate(wf["priorities"])}
    cands = [i for i in items if i["type"] in ("Task", "Bug") and i["status"] == "Ready"
             and i["state"] == "OPEN" and i["open_blockers"] == 0]
    cands.sort(key=lambda i: (order.get(i["priority"], 99), i["milestone_due"] or "9999", i["number"]))
    return cands[0] if cands else None


AC_TYPES = {"User Story", "Functional Requirement", "Non-Functional Requirement"}
_EXISTING = object()
KEY_LETTER = {"Epic": "E", "User Story": "S", "Functional Requirement": "F", "Non-Functional Requirement": "N", "Task": "T", "Bug": "B"}
KEY_RE = re.compile(r"[A-Z]\d{3}(\.[A-Z]\d{3})*")


def validate_plan(wf, plan):
    errs, seen = [], set()

    def walk(node, parent_type):
        k = node.get("key")
        if not k or k in seen:
            errs.append(f"key thiếu hoặc trùng: {k}")
        seen.add(k)
        t = node.get("type")
        if k and not (KEY_RE.fullmatch(k) and (t not in KEY_LETTER or k.split(".")[-1][0] == KEY_LETTER[t])):
            errs.append(f"key '{k}' phải dạng <chữ loại><NNN> nối bằng dấu chấm, ví dụ E001.S002.T003 "
                        "(E=Epic, S=User Story, F=Functional Requirement, N=Non-Functional Requirement, T=Task, B=Bug)")
        if t == "Change Request":
            errs.append(f"{k}: Change Request không tạo từ plan, dùng `new \"Change Request\" ...`")
        elif t not in wf["types"]:
            errs.append(f"{k}: loại '{t}' không thuộc workflow omi")
            return
        elif parent_type is not _EXISTING:
            try:
                check_parent(wf, t, parent_type)
            except RuleError as e:
                errs.append(f"{k}: {e}")
        if t in AC_TYPES and "acceptance criteria" not in node.get("body", "").lower():
            errs.append(f"{k}: thiếu mục '### Acceptance criteria'")
        if t == "Epic" and parent_type is None and not (node.get("milestone") or plan.get("milestone")):
            errs.append(f"{k}: Epic cần milestone (plan.milestone hoặc node.milestone)")
        for c in node.get("children", []):
            walk(c, t)

    for node in plan.get("items", []):
        walk(node, _EXISTING if "parent" in node else None)
    return errs
```

- [ ] **Step 4: Chạy test** — Expected: PASS.
- [ ] **Step 5: Commit** — `git commit -am "feat(rules): audit invariants, pick_next, validate_plan"`

### Task 006: Template chuẩn cho issue và PR (`templates.json`, `pr_template.json`)

**Files:**
- Create: `scripts/templates.json`, `scripts/pr_template.json`
- Modify: `scripts/rules.py`
- Test: `tests/test_rules.py`

**Interfaces:**
- Consumes: Task 005 (`validate_plan`).
- Produces:
  - `rules.load_templates(path=TEMPLATES_PATH) -> dict` (issue templates theo loại), `rules.load_pr_template(path=PR_TEMPLATE_PATH) -> dict`.
  - `rules.sections(body) -> dict[str, str]`, `rules.prefix(type_) -> str` (`"[<type>] "`), `rules.with_prefix(tpl, type_, title) -> str`, `rules.check_template(tpl, type_, title, body) -> list[str]`, `rules.check_pr(pr_tpl, title, body) -> list[str]`, `rules.fill(tpl, type_, fields: dict[str, str]) -> str`, `rules.skeleton(tpl, type_) -> str`.
  - `rules.validate_plan(wf, plan, tpl=None)`: có `tpl` thì kiểm template từng node (title được thêm prefix trước khi kiểm).
  - Cấu trúc template: `{"title": {"pattern", "example", "hint", "prefill"?}, "sections": [{"heading", "required", "hint"?, "default"?, "placeholder"?, "checklist"?, "options"?, "pattern"?}]}`. `pattern` của title áp dụng cho phần **sau** prefix. PR template: `{"title": {"pattern", "example", "hint"}, "sections": [...]}`.

- [ ] **Step 1: Viết `scripts/templates.json`**

Prefix title = `[<tên Issue Type đầy đủ>] ` do `rules.prefix()` sinh từ tên loại — không khai báo lặp trong JSON.

```json
{
  "Epic": {
    "title": {"pattern": "^\\S.{4,80}$", "example": "Quản lý đơn hàng", "hint": "Danh từ chỉ capability, 5–80 ký tự"},
    "sections": [
      {"heading": "Mục tiêu", "required": true, "hint": "Capability mang lại giá trị gì, cho ai"},
      {"heading": "Phạm vi", "required": true, "hint": "Gạch đầu dòng những gì thuộc Epic"},
      {"heading": "Ngoài phạm vi", "required": false, "hint": "Những gì không làm"},
      {"heading": "Chỉ số thành công", "required": false, "hint": "Đo thế nào là thành công"}
    ]
  },
  "User Story": {
    "title": {"pattern": "^.+ có thể .+$", "example": "Khách hàng có thể theo dõi trạng thái đơn hàng", "hint": "<Vai trò> có thể <hành động>"},
    "sections": [
      {"heading": "Story", "required": true, "default": "Là <vai trò>, tôi muốn <hành động> để <giá trị>.", "pattern": "^Là .+, tôi muốn .+ để .+"},
      {"heading": "Acceptance criteria", "required": true, "default": "- [ ] ", "checklist": true, "hint": "Mỗi dòng kiểm chứng được bằng test; không tự động được thì ghi [manual]"},
      {"heading": "Ghi chú", "required": false}
    ]
  },
  "Functional Requirement": {
    "title": {"pattern": "^Hệ thống (phải|cần) .+$", "example": "Hệ thống phải gửi email xác nhận khi đơn hàng được tạo", "hint": "Hệ thống phải <hành vi>", "prefill": "Hệ thống phải "},
    "sections": [
      {"heading": "Mô tả", "required": true, "hint": "Đầu vào → xử lý → đầu ra"},
      {"heading": "Acceptance criteria", "required": true, "default": "- [ ] ", "checklist": true, "hint": "Mỗi dòng kiểm chứng được bằng test; không tự động được thì ghi [manual]"},
      {"heading": "Ràng buộc", "required": false}
    ]
  },
  "Non-Functional Requirement": {
    "title": {"pattern": "^(Performance|Security|Reliability|Usability|Maintainability|Compliance): .+$", "example": "Performance: p95 API đặt hàng < 300ms ở 100 RPS", "hint": "<Nhóm>: <chỉ số> <ngưỡng>"},
    "sections": [
      {"heading": "Nhóm", "required": true, "options": ["Performance", "Security", "Reliability", "Usability", "Maintainability", "Compliance"]},
      {"heading": "Chỉ số và ngưỡng", "required": true, "hint": "Ví dụ: p95 < 300ms ở 100 RPS"},
      {"heading": "Cách đo", "required": true, "hint": "Công cụ/lệnh đo và môi trường"},
      {"heading": "Acceptance criteria", "required": true, "default": "- [ ] ", "checklist": true, "hint": "Mỗi dòng kiểm chứng được bằng test; không tự động được thì ghi [manual]"}
    ]
  },
  "Change Request": {
    "title": {"pattern": "^Thay đổi .+: .+$", "example": "Thay đổi thanh toán: hỗ trợ trả góp", "hint": "Thay đổi <đối tượng>: <tóm tắt>", "prefill": "Thay đổi "},
    "sections": [
      {"heading": "Lý do thay đổi", "required": true},
      {"heading": "Nội dung thay đổi", "required": true, "hint": "Trước → sau"},
      {"heading": "Affects", "required": true, "hint": "Item bị ảnh hưởng, ví dụ: #12 #15", "pattern": "#\\d+"},
      {"heading": "Ảnh hưởng dự kiến", "required": false}
    ]
  },
  "Task": {
    "title": {"pattern": "^\\S.{4,100}$", "example": "Thêm API POST /orders", "hint": "<Động từ> <đối tượng>, 5–100 ký tự"},
    "sections": [
      {"heading": "Việc cần làm", "required": true},
      {"heading": "Definition of done", "required": true, "default": "- [ ] Test pass\n- [ ] PR merged", "checklist": true, "placeholder": false},
      {"heading": "Ghi chú kỹ thuật", "required": false}
    ]
  },
  "Bug": {
    "title": {"pattern": "^.+: .+$", "example": "Giỏ hàng: tổng tiền sai khi áp mã giảm giá", "hint": "<Thành phần>: <triệu chứng>"},
    "sections": [
      {"heading": "Affects", "required": true, "hint": "Item bị ảnh hưởng, ví dụ: #42", "pattern": "#\\d+"},
      {"heading": "Môi trường", "required": false, "hint": "Phiên bản, OS, trình duyệt"},
      {"heading": "Các bước tái hiện", "required": true, "default": "1. "},
      {"heading": "Kết quả mong đợi", "required": true},
      {"heading": "Kết quả thực tế", "required": true}
    ]
  }
}
```

- [ ] **Step 2: Viết `scripts/pr_template.json`**

```json
{
  "title": {
    "pattern": "^\\[(Epic|User Story|Functional Requirement|Non-Functional Requirement|Change Request|Task|Bug)\\] .+ \\(#\\d+\\)$",
    "example": "[Task] Thêm API POST /orders (#12)",
    "hint": "<title issue, gồm prefix> (#<số issue>)"
  },
  "sections": [
    {"heading": "Liên kết", "required": true, "pattern": "(Closes|Fixes|Resolves) #\\d+", "hint": "Closes #<số issue>; Parent: #<số> <title>"},
    {"heading": "Thay đổi", "required": true, "hint": "Gạch đầu dòng các thay đổi chính"},
    {"heading": "Acceptance criteria liên quan", "required": false, "hint": "AC của parent mà PR này đáp ứng, kèm tên test ac<p>_<i>"},
    {"heading": "Kiểm thử", "required": true, "checklist": true, "default": "- [ ] lint/typecheck/scan/test pass\n- [ ] CI xanh", "placeholder": false},
    {"heading": "Security", "required": true, "options": ["Không chạm security", "Có chạm security"]}
  ]
}
```

- [ ] **Step 3: Thêm test vào `tests/test_rules.py`**

```python
TPL = rules.load_templates()
PR_TPL = rules.load_pr_template()
STORY_OK = "### Story\nLà khách, tôi muốn đặt hàng để mua nhanh.\n\n### Acceptance criteria\n- [ ] đặt được hàng"


class TestTemplates(unittest.TestCase):
    def test_every_workflow_type_has_template(self):
        self.assertEqual(set(TPL), set(WF["types"]))

    def test_prefix_full_names(self):
        self.assertEqual({rules.prefix(t) for t in TPL},
                         {"[Epic] ", "[User Story] ", "[Functional Requirement] ", "[Non-Functional Requirement] ",
                          "[Change Request] ", "[Task] ", "[Bug] "})

    def test_with_prefix_idempotent(self):
        self.assertEqual(rules.with_prefix(TPL, "Functional Requirement", "Hệ thống phải X"), "[Functional Requirement] Hệ thống phải X")
        self.assertEqual(rules.with_prefix(TPL, "Functional Requirement", "[Functional Requirement] Hệ thống phải X"),
                         "[Functional Requirement] Hệ thống phải X")

    def test_sections_parse(self):
        self.assertEqual(rules.sections("intro\n### A\nx\n\n### B\n_No response_\n### C\n<!-- gợi ý -->\n"),
                         {"A": "x", "B": "", "C": ""})

    def test_valid_story(self):
        self.assertEqual(rules.check_template(TPL, "User Story", "[User Story] Khách hàng có thể đặt hàng", STORY_OK), [])

    def test_missing_or_abbreviated_prefix(self):
        errs = rules.check_template(TPL, "User Story", "Khách hàng có thể đặt hàng", STORY_OK)
        self.assertEqual(len(errs), 1)
        self.assertIn("[User Story]", errs[0])
        errs = rules.check_template(TPL, "Functional Requirement", "[FR] Hệ thống phải gửi mail", "### Mô tả\nx\n\n### Acceptance criteria\n- [ ] y")
        self.assertTrue(any("[Functional Requirement]" in e for e in errs))

    def test_bad_title_pattern(self):
        errs = rules.check_template(TPL, "Functional Requirement", "[Functional Requirement] Gửi email",
                                    "### Mô tả\nx\n\n### Acceptance criteria\n- [ ] y")
        self.assertEqual(len(errs), 1)
        self.assertIn("Hệ thống phải", errs[0])

    def test_missing_and_default_sections(self):
        errs = rules.check_template(TPL, "User Story", "[User Story] Khách có thể mua",
                                    "### Story\nLà <vai trò>, tôi muốn <hành động> để <giá trị>.")
        self.assertTrue(any("Story" in e for e in errs))
        self.assertTrue(any("Acceptance criteria" in e for e in errs))

    def test_checklist_options_pattern(self):
        self.assertTrue(rules.check_template(TPL, "Task", "[Task] Thêm API đặt hàng",
                                             "### Việc cần làm\nx\n\n### Definition of done\nchỉ chữ"))
        nfr = ("### Nhóm\nNhanh\n\n### Chỉ số và ngưỡng\np95<300ms\n\n### Cách đo\nk6\n\n"
               "### Acceptance criteria\n- [ ] đạt")
        self.assertTrue(any("Nhóm" in e for e in rules.check_template(
            TPL, "Non-Functional Requirement", "[Non-Functional Requirement] Performance: p95 < 300ms", nfr)))
        self.assertTrue(any("Affects" in e for e in rules.check_template(
            TPL, "Bug", "[Bug] Giỏ hàng: sai tổng", "### Affects\nkhông có số\n\n### Các bước tái hiện\n1. a\n\n"
                                                   "### Kết quả mong đợi\na\n\n### Kết quả thực tế\nb")))

    def test_fill_builds_valid_task_body(self):
        body = rules.fill(TPL, "Task", {"Việc cần làm": "Thêm API POST /orders"})
        self.assertIn("### Definition of done\n- [ ] Test pass", body)
        self.assertEqual(rules.check_template(TPL, "Task", "[Task] Thêm API POST /orders", body), [])
        with self.assertRaisesRegex(RuleError, "không có mục"):
            rules.fill(TPL, "Task", {"Sai": "x"})

    def test_skeleton(self):
        sk = rules.skeleton(TPL, "Bug")
        self.assertTrue(sk.startswith("Title: [Bug] <Thành phần>: <triệu chứng>"))
        self.assertIn("### Các bước tái hiện", sk)

    def test_validate_plan_with_templates(self):
        plan = {"milestone": "v1", "items": [{"key": "E001", "type": "Epic", "title": "E", "children": []}]}
        errs = rules.validate_plan(WF, plan, TPL)
        self.assertTrue(any("E001: Title" in e for e in errs))
        self.assertTrue(any("E001: Thiếu mục '### Mục tiêu'" in e for e in errs))
        ok = {"milestone": "v1", "items": [{"key": "E001", "type": "Epic", "title": "Quản lý đơn hàng",
                                            "body": "### Mục tiêu\nx\n\n### Phạm vi\n- y"}]}
        self.assertEqual(rules.validate_plan(WF, ok, TPL), [])  # title không prefix: được thêm trước khi kiểm


PR_BODY = ("### Liên kết\nCloses #12\n\n### Thay đổi\n- thêm API\n\n### Kiểm thử\n- [x] check pass\n\n"
           "### Security\nKhông chạm security")


class TestPrTemplate(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(rules.check_pr(PR_TPL, "[Task] Thêm API POST /orders (#12)", PR_BODY), [])

    def test_invalid(self):
        errs = rules.check_pr(PR_TPL, "Thêm API", PR_BODY.replace("Closes #12", "liên quan task"))
        self.assertTrue(any("Title PR" in e for e in errs))
        self.assertTrue(any("Liên kết" in e for e in errs))
        self.assertTrue(rules.check_pr(PR_TPL, "[FR] X (#1)", PR_BODY))  # prefix viết tắt bị từ chối
```

- [ ] **Step 4: Chạy để thấy thất bại** — Expected: `AttributeError ... 'load_templates'`.

- [ ] **Step 5: Thêm vào `scripts/rules.py`**

```python
TEMPLATES_PATH = Path(__file__).with_name("templates.json")
PR_TEMPLATE_PATH = Path(__file__).with_name("pr_template.json")
_EMPTY = {"", "_No response_"}


def load_templates(path=TEMPLATES_PATH):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_pr_template(path=PR_TEMPLATE_PATH):
    return json.loads(Path(path).read_text(encoding="utf-8"))


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
    _type_tpl = tpl[type_]  # KeyError nếu loại không có template
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
```

`skeleton` gắn " (tùy chọn)" vào heading chỉ để hướng dẫn; khi điền giữ đúng tên heading.

Sửa `validate_plan` (Task 005): đổi chữ ký thành `def validate_plan(wf, plan, tpl=None):` và trong `walk`, ngay sau khối kiểm `AC_TYPES`, thêm:

```python
        if tpl and t in tpl:
            body = node.get("body", "")
            if node.get("affects"):
                body += "\n\n### Affects\n" + " ".join(f"#{a}" for a in node["affects"])
            title = with_prefix(tpl, t, node.get("title", ""))
            errs.extend(f"{k}: {e}" for e in check_template(tpl, t, title, body))
```

- [ ] **Step 6: Chạy test** — Expected: PASS (các test `TestValidatePlan` cũ không truyền `tpl` nên không đổi).
- [ ] **Step 7: Commit** — `git add scripts/templates.json scripts/pr_template.json scripts/rules.py tests/test_rules.py && git commit -m "feat(rules): template chuẩn cho issue (prefix đầy đủ) và PR"`

---

## Phase 2 — Lớp GitHub (`gh.py`)

### Task 007: Gọi `gh`, snapshot, project items, ghi field

**Files:**
- Create: `scripts/gh.py`, `tests/test_gh.py`

**Interfaces:**
- Produces:
  - `gh.GhError(Exception)`, `gh.run(args: list[str], input: str|None=None) -> str`, `gh.graphql(query: str, **variables) -> dict`, `gh.rest(method: str, path: str, body: dict|None=None) -> dict|list|None`.
  - `gh.FIELD_KINDS: dict[str, "single"|"number"|"text"]`, `gh.AUDIT_TITLE = "OMI Audit"`.
  - `gh.normalize_issue(raw: dict, project_id: str) -> dict` → snapshot với khóa: `id, number, title, body, type, state, state_reason, milestone, labels (list[str]), item_id, status, rework_count, blocked_reason, parent, children (mỗi con: number, title, type, state, status), open_blockers, prs`.
  - `gh.issue_snapshot(cfg, number) -> dict`, `gh.normalize_project_item(node: dict) -> dict|None`, `gh.project_items(cfg) -> list[dict]`.
  - `gh.set_field(cfg, item_id, field, value)`, `gh.clear_field(cfg, item_id, field)`, `gh.find_item(cfg, node_id) -> str|None`, `gh.add_to_project(cfg, node_id) -> str` (chịu được việc GitHub tự thêm sub-issue). `gh.run(args, input=None, cwd=None)`.
  - `cfg` = nội dung `.omi/project.json`: `{"owner","repo","project_number","project_id","fields": {name: {"id", "options"?: {optName: optId}}}}`.

- [ ] **Step 1: Viết test thất bại `tests/test_gh.py`**

```python
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import gh  # noqa: E402

PID = "PROJ"


def pitem(pid=PID, status=None, rework=None, blocked=None, iid="ITEM"):
    return {"id": iid, "project": {"id": pid},
            "status": {"name": status} if status else None,
            "rework": {"number": rework} if rework is not None else None,
            "blocked": {"text": blocked} if blocked else None}


RAW = {
    "id": "I_1", "number": 7, "title": "Làm X", "body": "b", "state": "OPEN", "stateReason": None,
    "issueType": {"name": "Task"}, "milestone": {"title": "v1"}, "labels": {"nodes": [{"name": "security"}]},
    "parent": {"number": 3, "issueType": {"name": "Functional Requirement"}, "projectItems": {"nodes": [pitem(status="Approved")]}},
    "subIssues": {"nodes": []},
    "blockedBy": {"nodes": [{"number": 1, "state": "OPEN"}, {"number": 2, "state": "CLOSED"}]},
    "closedByPullRequestsReferences": {"nodes": [{"number": 9, "state": "OPEN", "merged": False}]},
    "projectItems": {"nodes": [pitem(pid="OTHER", status="Done", iid="X"),
                               pitem(status="In Review", rework=2.0, iid="ITEM")]},
}


class TestNormalize(unittest.TestCase):
    def test_issue(self):
        s = gh.normalize_issue(RAW, PID)
        self.assertEqual(s["type"], "Task")
        self.assertEqual(s["item_id"], "ITEM")
        self.assertEqual(s["status"], "In Review")
        self.assertEqual(s["rework_count"], 2)
        self.assertEqual(s["parent"], {"number": 3, "type": "Functional Requirement", "status": "Approved"})
        self.assertEqual(s["open_blockers"], 1)
        self.assertEqual(s["prs"], [{"number": 9, "state": "OPEN", "merged": False}])
        self.assertEqual(s["milestone"], "v1")
        self.assertEqual(s["labels"], ["security"])

    def test_issue_not_in_project(self):
        raw = dict(RAW, projectItems={"nodes": []}, parent=None, issueType=None, milestone=None)
        s = gh.normalize_issue(raw, PID)
        self.assertIsNone(s["item_id"])
        self.assertIsNone(s["status"])
        self.assertIsNone(s["type"])
        self.assertEqual(s["rework_count"], 0)

    def test_project_item(self):
        node = {"id": "ITEM", "status": {"name": "Ready"}, "priority": {"name": "P1"}, "blocked": None,
                "content": {"id": "I_7", "number": 7, "title": "t", "state": "OPEN", "stateReason": None,
                            "issueType": {"name": "Task"}, "milestone": {"title": "v1", "dueOn": "2026-12-01T00:00:00Z"},
                            "parent": {"number": 3}, "blockedBy": {"nodes": [{"state": "OPEN"}]}}}
        it = gh.normalize_project_item(node)
        self.assertEqual((it["number"], it["status"], it["priority"], it["parent"], it["open_blockers"]),
                         (7, "Ready", "P1", 3, 1))
        self.assertEqual(it["milestone_due"], "2026-12-01T00:00:00Z")
        self.assertTrue(it["in_project"])

    def test_project_item_skips_non_issue(self):
        self.assertIsNone(gh.normalize_project_item({"id": "X", "content": {}}))


CFG = {"owner": "o", "repo": "r", "project_id": PID, "fields": {
    "Status": {"id": "F_S", "options": {"Ready": "OPT_R"}},
    "Rework Count": {"id": "F_R"}, "Blocked Reason": {"id": "F_B"}}}


class TestSetField(unittest.TestCase):
    def test_single_select(self):
        with mock.patch.object(gh, "graphql") as g:
            gh.set_field(CFG, "ITEM", "Status", "Ready")
        self.assertEqual(g.call_args.kwargs["value"], {"singleSelectOptionId": "OPT_R"})

    def test_number_and_text(self):
        with mock.patch.object(gh, "graphql") as g:
            gh.set_field(CFG, "ITEM", "Rework Count", 2)
            self.assertEqual(g.call_args.kwargs["value"], {"number": 2.0})
            gh.set_field(CFG, "ITEM", "Blocked Reason", "chờ")
            self.assertEqual(g.call_args.kwargs["value"], {"text": "chờ"})

    def test_add_to_project_when_github_auto_added(self):
        with mock.patch.object(gh, "graphql", side_effect=[
                gh.GhError("Content already exists in this project"),
                {"node": {"projectItems": {"nodes": [{"id": "ITEM9", "project": {"id": PID}}]}}}]):
            self.assertEqual(gh.add_to_project(CFG, "I_9"), "ITEM9")

    def test_unknown_option(self):
        with self.assertRaisesRegex(gh.GhError, "không có option"):
            gh.set_field(CFG, "ITEM", "Status", "Nope")


class TestRun(unittest.TestCase):
    def test_error_hint(self):
        fake = mock.Mock(returncode=1, stdout="", stderr="INSUFFICIENT_SCOPES: need project")
        with mock.patch("subprocess.run", return_value=fake):
            with self.assertRaisesRegex(gh.GhError, "gh auth refresh"):
                gh.run(["api", "graphql"])

    def test_graphql_sends_json(self):
        fake = mock.Mock(returncode=0, stdout=json.dumps({"data": {"ok": 1}}), stderr="")
        with mock.patch("subprocess.run", return_value=fake) as r:
            self.assertEqual(gh.graphql("query{x}", a=1), {"ok": 1})
        self.assertEqual(json.loads(r.call_args.kwargs["input"]), {"query": "query{x}", "variables": {"a": 1}})


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Chạy để thấy thất bại** — Expected: `ModuleNotFoundError: No module named 'gh'`.

- [ ] **Step 3: Viết `scripts/gh.py` (phần lõi)**

Nếu Task 001 ghi nhận tên field GraphQL khác, sửa query ở đây cho khớp.

```python
"""Lớp duy nhất gọi gh CLI. Mọi hàm trả dữ liệu Python thuần."""
import json
import re
import subprocess
import time

FIELD_KINDS = {"Status": "single", "Priority": "single", "Estimate": "number",
               "Rework Count": "number", "Blocked Reason": "text"}
AUDIT_TITLE = "OMI Audit"
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


def _r(cfg):
    return f"repos/{cfg['owner']}/{cfg['repo']}"


def _repo(cfg):
    return f"{cfg['owner']}/{cfg['repo']}"


# ---------- đọc ----------
_ITEM_FIELDS = """
  status: fieldValueByName(name: "Status") { ... on ProjectV2ItemFieldSingleSelectValue { name } }
  rework: fieldValueByName(name: "Rework Count") { ... on ProjectV2ItemFieldNumberValue { number } }
  blocked: fieldValueByName(name: "Blocked Reason") { ... on ProjectV2ItemFieldTextValue { text } }
"""
_STATUS_ONLY = 'projectItems(first: 10) { nodes { id project { id } status: fieldValueByName(name: "Status") { ... on ProjectV2ItemFieldSingleSelectValue { name } } } }'

SNAPSHOT_QUERY = f"""
query($owner: String!, $repo: String!, $number: Int!) {{
  repository(owner: $owner, name: $repo) {{
    issue(number: $number) {{
      id number title body state stateReason
      issueType {{ name }}
      milestone {{ title }}
      labels(first: 20) {{ nodes {{ name }} }}
      parent {{ number issueType {{ name }} {_STATUS_ONLY} }}
      subIssues(first: 100) {{ nodes {{ number title state issueType {{ name }} {_STATUS_ONLY} }} }}
      blockedBy(first: 50) {{ nodes {{ number state }} }}
      closedByPullRequestsReferences(first: 10, includeClosedPrs: true) {{ nodes {{ number state merged }} }}
      projectItems(first: 10) {{ nodes {{ id project {{ id }} {_ITEM_FIELDS} }} }}
    }}
  }}
}}"""


def _proj(nodes, project_id):
    return next((x for x in nodes if x["project"]["id"] == project_id), None)


def _val(it, key, sub):
    v = (it or {}).get(key)
    return v.get(sub) if v else None


def _tname(node):
    return (node.get("issueType") or {}).get("name")


def _status_of(node, project_id):
    return _val(_proj(node["projectItems"]["nodes"], project_id), "status", "name")


def normalize_issue(raw, project_id):
    it = _proj(raw["projectItems"]["nodes"], project_id)
    p = raw.get("parent")
    return {
        "id": raw["id"], "number": raw["number"], "title": raw["title"], "body": raw["body"],
        "type": _tname(raw), "state": raw["state"], "state_reason": raw.get("stateReason"),
        "milestone": (raw.get("milestone") or {}).get("title"),
        "labels": [x["name"] for x in (raw.get("labels") or {}).get("nodes", [])],
        "item_id": it["id"] if it else None,
        "status": _val(it, "status", "name"),
        "rework_count": int(_val(it, "rework", "number") or 0),
        "blocked_reason": _val(it, "blocked", "text"),
        "parent": ({"number": p["number"], "type": _tname(p), "status": _status_of(p, project_id)} if p else None),
        "children": [{"number": c["number"], "title": c.get("title"), "type": _tname(c), "state": c["state"],
                      "status": _status_of(c, project_id)} for c in raw["subIssues"]["nodes"]],
        "open_blockers": sum(1 for b in raw["blockedBy"]["nodes"] if b["state"] == "OPEN"),
        "prs": [{"number": x["number"], "state": x["state"], "merged": x["merged"]}
                for x in raw["closedByPullRequestsReferences"]["nodes"]],
    }


def issue_snapshot(cfg, number):
    d = graphql(SNAPSHOT_QUERY, owner=cfg["owner"], repo=cfg["repo"], number=number)
    raw = d["repository"]["issue"]
    if raw is None:
        raise GhError(f"Không tìm thấy issue #{number}")
    return normalize_issue(raw, cfg["project_id"])


ITEMS_QUERY = """
query($id: ID!, $after: String) {
  node(id: $id) { ... on ProjectV2 { items(first: 100, after: $after) {
    pageInfo { hasNextPage endCursor }
    nodes { id
      status: fieldValueByName(name: "Status") { ... on ProjectV2ItemFieldSingleSelectValue { name } }
      priority: fieldValueByName(name: "Priority") { ... on ProjectV2ItemFieldSingleSelectValue { name } }
      rework: fieldValueByName(name: "Rework Count") { ... on ProjectV2ItemFieldNumberValue { number } }
      blocked: fieldValueByName(name: "Blocked Reason") { ... on ProjectV2ItemFieldTextValue { text } }
      content { ... on Issue { id number title state stateReason issueType { name }
        milestone { title dueOn } parent { number } blockedBy(first: 50) { nodes { state } } } }
    } } } }
}"""


def normalize_project_item(node):
    c = node.get("content") or {}
    if "number" not in c:
        return None  # draft issue hoặc PR
    ms = c.get("milestone") or {}
    return {
        "item_id": node["id"], "id": c["id"], "number": c["number"], "title": c["title"],
        "type": _tname(c), "state": c["state"], "state_reason": c.get("stateReason"),
        "status": _val(node, "status", "name"), "priority": _val(node, "priority", "name"),
        "rework_count": int(_val(node, "rework", "number") or 0),
        "blocked_reason": _val(node, "blocked", "text"),
        "milestone": ms.get("title"), "milestone_due": ms.get("dueOn"),
        "parent": (c.get("parent") or {}).get("number"),
        "open_blockers": sum(1 for b in c["blockedBy"]["nodes"] if b["state"] == "OPEN"),
        "in_project": True,
    }


def project_items(cfg):
    out, after = [], None
    while True:
        page = graphql(ITEMS_QUERY, id=cfg["project_id"], after=after)["node"]["items"]
        out += [i for i in map(normalize_project_item, page["nodes"]) if i]
        if not page["pageInfo"]["hasNextPage"]:
            return out
        after = page["pageInfo"]["endCursor"]


# ---------- ghi field ----------
SET_FIELD = """mutation($project: ID!, $item: ID!, $field: ID!, $value: ProjectV2FieldValue!) {
  updateProjectV2ItemFieldValue(input: {projectId: $project, itemId: $item, fieldId: $field, value: $value}) {
    projectV2Item { id } } }"""
CLEAR_FIELD = """mutation($project: ID!, $item: ID!, $field: ID!) {
  clearProjectV2ItemFieldValue(input: {projectId: $project, itemId: $item, fieldId: $field}) {
    projectV2Item { id } } }"""
ADD_ITEM = """mutation($project: ID!, $content: ID!) {
  addProjectV2ItemById(input: {projectId: $project, contentId: $content}) { item { id } } }"""


def set_field(cfg, item_id, field, value):
    f, kind = cfg["fields"][field], FIELD_KINDS[field]
    if kind == "single":
        if value not in f["options"]:
            raise GhError(f"Field {field} không có option '{value}'")
        val = {"singleSelectOptionId": f["options"][value]}
    elif kind == "number":
        val = {"number": float(value)}
    else:
        val = {"text": str(value)}
    graphql(SET_FIELD, project=cfg["project_id"], item=item_id, field=f["id"], value=val)


def clear_field(cfg, item_id, field):
    graphql(CLEAR_FIELD, project=cfg["project_id"], item=item_id, field=cfg["fields"][field]["id"])


FIND_ITEM = """query($id: ID!) { node(id: $id) { ... on Issue {
  projectItems(first: 10) { nodes { id project { id } } } } } }"""


def find_item(cfg, node_id):
    nodes = graphql(FIND_ITEM, id=node_id)["node"]["projectItems"]["nodes"]
    return next((x["id"] for x in nodes if x["project"]["id"] == cfg["project_id"]), None)


def add_to_project(cfg, node_id):
    """GitHub tự thêm sub-issue của item đã trong Project (bất đồng bộ) → add báo 'already exists': tìm lại item."""
    for _ in range(6):
        try:
            return graphql(ADD_ITEM, project=cfg["project_id"], content=node_id)["addProjectV2ItemById"]["item"]["id"]
        except GhError as e:
            if "already exists" not in str(e):
                raise
        item = find_item(cfg, node_id)
        if item:
            return item
        time.sleep(2)
    raise GhError(f"Không lấy được item Project cho {node_id}")
```

- [ ] **Step 4: Chạy test** — Run: `python -m unittest discover -s tests -v` — Expected: PASS.

- [ ] **Step 5: Kiểm tra query thật với sandbox** (dùng issue `$C` từ Task 001)

```bash
python -c "import sys; sys.path.insert(0,'scripts'); import gh, json; print(json.dumps(gh.graphql(gh.SNAPSHOT_QUERY, owner='omi-home', repo='omi-sandbox', number=<C>), indent=1, ensure_ascii=False)[:1500])"
```
Expected: JSON không có `errors`, có `parent`, `blockedBy`.

- [ ] **Step 6: Commit**

```bash
git add scripts/gh.py tests/test_gh.py
git commit -m "feat(gh): wrapper gh, snapshot issue, project items, ghi field"
```

### Task 008: Thao tác issue, milestone, bootstrap

**Files:**
- Modify: `scripts/gh.py` (thêm cuối file)

**Interfaces:**
- Consumes: Task 007.
- Produces:
  - Issue: `create_issue(cfg, title, body, type_, milestone=None) -> dict` (REST issue: `number`, `id` số, `node_id`), `issue_db_id(cfg, n) -> int`, `add_sub_issue(cfg, parent_n, child_db_id)`, `add_blocked_by(cfg, n, blocker_db_id)`, `comment(cfg, n, body)`, `comments(cfg, n) -> list[str]`, `close(cfg, n, reason: "completed"|"not_planned")`, `assign_self(cfg, n)`, `existing_keys(cfg) -> dict[str, int]`, `repo_issues(cfg) -> list[{"number","title","state"}]`, `upsert_audit_issue(cfg, body: str|None)`.
  - Milestone: `milestone_number(cfg, title) -> int`, `ensure_milestone(cfg, title) -> int`, `set_milestone(cfg, n, title)`.
  - Bootstrap: `current_repo(cwd=None) -> (owner, repo)`, `set_variable(cfg, name, value)`, `ensure_issue_types(org, names)`, `find_project(owner, title) -> int|None`, `create_project(owner, title) -> int`, `copy_project(owner, source, title) -> int`, `project_node_id(owner, number) -> str`, `default_branch(owner, repo) -> str`, `ensure_label(cfg, name)`, `link_project(owner, number, repo_full)`, `ensure_fields(owner, number, wf)`, `load_fields(owner, number) -> dict`.

- [ ] **Step 1: Thêm vào `scripts/gh.py`**

```python
# ---------- issue ----------
def milestone_number(cfg, title):
    for m in rest("GET", f"{_r(cfg)}/milestones?state=all&per_page=100"):
        if m["title"] == title:
            return m["number"]
    raise GhError(f"Milestone '{title}' không tồn tại")


def ensure_milestone(cfg, title):
    try:
        return milestone_number(cfg, title)
    except GhError:
        return rest("POST", f"{_r(cfg)}/milestones", {"title": title})["number"]


def set_milestone(cfg, n, title):
    rest("PATCH", f"{_r(cfg)}/issues/{n}", {"milestone": milestone_number(cfg, title)})


def create_issue(cfg, title, body, type_, milestone=None):
    data = {"title": title, "body": body, "type": type_}
    if milestone:
        data["milestone"] = milestone_number(cfg, milestone)
    return rest("POST", f"{_r(cfg)}/issues", data)


def issue_db_id(cfg, n):
    return rest("GET", f"{_r(cfg)}/issues/{n}")["id"]


def add_sub_issue(cfg, parent_n, child_db_id):
    rest("POST", f"{_r(cfg)}/issues/{parent_n}/sub_issues", {"sub_issue_id": child_db_id})


def add_blocked_by(cfg, n, blocker_db_id):
    rest("POST", f"{_r(cfg)}/issues/{n}/dependencies/blocked_by", {"issue_id": blocker_db_id})


def comment(cfg, n, body):
    rest("POST", f"{_r(cfg)}/issues/{n}/comments", {"body": body})


def comments(cfg, n):
    pages = json.loads(run(["api", "--paginate", "--slurp", f"{_r(cfg)}/issues/{n}/comments?per_page=100"]))
    return [c["body"] for page in pages for c in page]


def close(cfg, n, reason):
    rest("PATCH", f"{_r(cfg)}/issues/{n}", {"state": "closed", "state_reason": reason})


def assign_self(cfg, n):
    run(["issue", "edit", str(n), "-R", _repo(cfg), "--add-assignee", "@me"])


def repo_issues(cfg):
    # ponytail: tối đa 1000 issue; chuyển sang phân trang GraphQL khi repo lớn hơn
    return json.loads(run(["issue", "list", "-R", _repo(cfg), "--state", "all", "--limit", "1000",
                           "--json", "number,title,state"]))


def existing_keys(cfg):
    out = json.loads(run(["issue", "list", "-R", _repo(cfg), "--state", "all", "--limit", "1000",
                          "--json", "number,body"]))
    keys = {}
    for i in out:
        m = re.search(r"<!-- omi:key=(\S+) -->", i["body"] or "")
        if m:
            keys[m.group(1)] = i["number"]
    return keys


def upsert_audit_issue(cfg, body):
    found = [i for i in repo_issues(cfg) if i["title"] == AUDIT_TITLE and i["state"] == "OPEN"]
    if body is None:
        for i in found:
            close(cfg, i["number"], "completed")
    elif found:
        rest("PATCH", f"{_r(cfg)}/issues/{found[0]['number']}", {"body": body})
    else:
        rest("POST", f"{_r(cfg)}/issues", {"title": AUDIT_TITLE, "body": body})


# ---------- bootstrap ----------
STATUS_COLORS = {"Draft": "GRAY", "Triage": "PINK", "Approved": "PURPLE", "Ready": "BLUE",
                 "In Progress": "YELLOW", "In Review": "ORANGE", "In QA": "ORANGE",
                 "Blocked": "RED", "Done": "GREEN", "Cancelled": "GRAY"}
UPDATE_STATUS = """mutation($field: ID!, $options: [ProjectV2SingleSelectFieldOptionInput!]) {
  updateProjectV2Field(input: {fieldId: $field, singleSelectOptions: $options}) {
    projectV2Field { ... on ProjectV2SingleSelectField { id } } } }"""


def current_repo(cwd=None):
    d = json.loads(run(["repo", "view", "--json", "owner,name"], cwd=cwd))
    return d["owner"]["login"], d["name"]


def set_variable(cfg, name, value):
    run(["variable", "set", name, "-R", _repo(cfg), "--body", value])


def ensure_issue_types(org, names):
    try:
        existing = {t["name"] for t in rest("GET", f"orgs/{org}/issue-types")}
    except GhError as e:
        raise GhError(f"Không đọc được Issue Types của '{org}'. omi-hub cần repo thuộc Organization "
                      f"và token có admin:org. Chi tiết: {e}") from None
    for name in names:
        if name not in existing:
            rest("POST", f"orgs/{org}/issue-types", {"name": name, "is_enabled": True})


def find_project(owner, title):
    d = json.loads(run(["project", "list", "--owner", owner, "--format", "json", "--limit", "200"]))
    return next((p["number"] for p in d["projects"] if p["title"] == title), None)


def create_project(owner, title):
    return json.loads(run(["project", "create", "--owner", owner, "--title", title, "--format", "json"]))["number"]


def copy_project(owner, source, title):
    return json.loads(run(["project", "copy", str(source), "--source-owner", owner, "--target-owner", owner,
                           "--title", title, "--format", "json"]))["number"]


def project_node_id(owner, number):
    return json.loads(run(["project", "view", str(number), "--owner", owner, "--format", "json"]))["id"]


def default_branch(owner, repo):
    return run(["repo", "view", f"{owner}/{repo}", "--json", "defaultBranchRef",
                "-q", ".defaultBranchRef.name"]).strip()


def ensure_label(cfg, name):
    run(["label", "create", name, "-R", _repo(cfg), "--force", "--color", "B60205",
         "--description", "Chạm security: bật security review"])


def link_project(owner, number, repo_full):
    run(["project", "link", str(number), "--owner", owner, "--repo", repo_full])


def _field_list(owner, number):
    return json.loads(run(["project", "field-list", str(number), "--owner", owner,
                           "--format", "json", "--limit", "100"]))["fields"]


def ensure_fields(owner, number, wf):
    fields = {f["name"]: f for f in _field_list(owner, number)}
    status = fields["Status"]
    if [o["name"] for o in status.get("options", [])] != wf["statuses"]:
        items = json.loads(run(["project", "item-list", str(number), "--owner", owner,
                                "--format", "json", "--limit", "1"]))["items"]
        if items:
            raise GhError(f"Status của Project #{number} khác chuẩn omi và đã có item. "
                          f"Sửa tay options Status thành: {', '.join(wf['statuses'])}")
        graphql(UPDATE_STATUS, field=status["id"],
                options=[{"name": s, "color": STATUS_COLORS[s], "description": ""} for s in wf["statuses"]])
    wanted = {"Priority": ("SINGLE_SELECT", ",".join(wf["priorities"])), "Estimate": ("NUMBER", None),
              "Rework Count": ("NUMBER", None), "Blocked Reason": ("TEXT", None)}
    for name, (dtype, opts) in wanted.items():
        if name not in fields:
            args = ["project", "field-create", str(number), "--owner", owner, "--name", name, "--data-type", dtype]
            if opts:
                args += ["--single-select-options", opts]
            run(args)


def load_fields(owner, number):
    out = {}
    for f in _field_list(owner, number):
        if f["name"] in FIELD_KINDS:
            out[f["name"]] = {"id": f["id"]}
            if f.get("options"):
                out[f["name"]]["options"] = {o["name"]: o["id"] for o in f["options"]}
    return out
```

- [ ] **Step 2: Chạy toàn bộ unit test** — Expected: PASS (không đổi hành vi đã test).

- [ ] **Step 3: Smoke test trên sandbox** (từ clone `omi-sandbox`)

```bash
python -c "import sys; sys.path.insert(0,r'<omi-hub>/scripts'); import gh; print(gh.current_repo('omi-sandbox')); print(len(gh.repo_issues({'owner':'omi-home','repo':'omi-sandbox'})))"
```
Expected: `('omi-home', 'omi-sandbox')` và một số ≥ 2.

- [ ] **Step 4: Commit** — `git commit -am "feat(gh): thao tác issue, milestone, bootstrap project"`

---

## Phase 3 — CLI (`omi.py`)

### Task 009: Helper text thuần

**Files:**
- Create: `scripts/omi.py` (phần đầu), `tests/test_cli.py`

**Interfaces:**
- Produces: `omi.build_body(body: str, affects=(), key=None) -> str`, `omi.find_marker(texts: list[str], name: str) -> str|True|None` (giá trị marker cuối cùng), `omi.affected(body: str) -> list[int]`, `omi.merge_agents_md(existing: str, section: str) -> str`, hằng `omi.BEGIN`, `omi.END`, `omi.CONFIG`, `omi.TEMPLATES`.

- [ ] **Step 1: Viết test thất bại `tests/test_cli.py`**

```python
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import omi  # noqa: E402


class TestText(unittest.TestCase):
    def test_build_body(self):
        self.assertEqual(omi.build_body("Mô tả", [12, 15], "E001.S001"),
                         "Mô tả\n\n### Affects\n#12 #15\n\n<!-- omi:key=E001.S001 -->")
        self.assertEqual(omi.build_body("  "), "")

    def test_affected_roundtrip(self):
        self.assertEqual(omi.affected(omi.build_body("x", [3, 4])), [3, 4])
        self.assertEqual(omi.affected("không có"), [])

    def test_find_marker_last_wins(self):
        texts = ["<!-- omi:blocked-from=Ready -->\n🚧", "khác", "<!-- omi:blocked-from=In Progress -->"]
        self.assertEqual(omi.find_marker(texts, "blocked-from"), "In Progress")
        self.assertIs(omi.find_marker(["a <!-- omi:impact --> b"], "impact"), True)
        self.assertIsNone(omi.find_marker(["<!-- omi:rework n=1 stage=qa -->"], "impact"))

    def test_merge_agents_md(self):
        sec = f"{omi.BEGIN}\nmới\n{omi.END}"
        self.assertEqual(omi.merge_agents_md("", sec), sec + "\n")
        self.assertEqual(omi.merge_agents_md("# Dự án\n", sec), "# Dự án\n\n" + sec + "\n")
        old = f"# Dự án\n\n{omi.BEGIN}\ncũ\n{omi.END}\n\n## Khác\n"
        self.assertEqual(omi.merge_agents_md(old, sec), f"# Dự án\n\n{sec}\n\n## Khác\n")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Chạy để thấy thất bại** — Expected: `ModuleNotFoundError: No module named 'omi'`.

- [ ] **Step 3: Viết `scripts/omi.py` phần đầu**

```python
#!/usr/bin/env python3
"""omi — CLI quản lý work item trên GitHub Projects theo workflow omi-hub."""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gh  # noqa: E402
import rules  # noqa: E402
from rules import RuleError  # noqa: E402

CONFIG = Path(".omi/project.json")
TMP = Path(".omi/tmp")
TEMPLATES = Path(__file__).resolve().parents[1] / "templates"
DEFAULT_SECURITY = ["auth", "login", "password", "secret", "token", "crypto", "permission", "acl",
                    "session", r"\.env", "sql"]
BEGIN, END = "<!-- omi:begin -->", "<!-- omi:end -->"
MARKER = re.compile(r"<!-- omi:(\S+?)(?:=(.*?))? -->")


# ---------- helper thuần ----------
def build_body(body, affects=(), key=None):
    parts = [body.strip()] if body.strip() else []
    if affects and "### Affects" not in body:
        parts.append("### Affects\n" + " ".join(f"#{n}" for n in affects))
    if key:
        parts.append(f"<!-- omi:key={key} -->")
    return "\n\n".join(parts)


def affected(body):
    m = re.search(r"^### Affects\s*\n(.+)$", body or "", re.M)
    return [int(x) for x in re.findall(r"#(\d+)", m.group(1))] if m else []


def find_marker(texts, name):
    found = None
    for t in texts:
        for m in MARKER.finditer(t or ""):
            if m.group(1) == name:
                found = m.group(2) if m.group(2) is not None else True
    return found


def merge_agents_md(existing, section):
    section = section.strip()
    if BEGIN in existing and END in existing:
        head, rest = existing.split(BEGIN, 1)
        _, tail = rest.split(END, 1)
        return head + section + tail
    return (existing.rstrip() + "\n\n" if existing.strip() else "") + section + "\n"
```

- [ ] **Step 4: Chạy test** — Expected: PASS.
- [ ] **Step 5: Commit** — `git add scripts/omi.py tests/test_cli.py && git commit -m "feat(cli): helper text thuần"`

### Task 010: Lệnh new, move, rework, block, unblock, tree, next + rollup

**Files:**
- Modify: `scripts/omi.py` (thêm cuối file)
- Create: `tests/test_cli_flow.py`

**Interfaces:**
- Consumes: `rules.*` (Task 002–005), `gh.*` (Task 007–008), helper Task 009.
- Produces: `omi.find_root(start=None) -> Path|None`, `omi.load_cfg() -> dict` (thêm `_root`, đặt `TMP` = `<workspace>/.omi/tmp`), `omi.repo_dir(cfg) -> Path`, `omi.snapshot(cfg, n) -> dict` (bắt buộc đã vào Project), `omi.apply_status(cfg, wf, snap, target, reason=None)`, `omi.rollup_up(cfg, wf, snap, trigger)`, `omi.cmd_new(cfg, wf, type_, title, parent=None, affects=(), milestone=None, priority=None, estimate=None, body="", key=None, status=None) -> int`, `omi.cmd_move(cfg, wf, n, target, reason=None)`, `omi.cmd_rework(cfg, wf, n, reason) -> str`, `omi.cmd_block(cfg, wf, n, reason=None, by=None)`, `omi.cmd_unblock(cfg, wf, n)`, `omi.cmd_tree(cfg, n=None)`, `omi.cmd_next(cfg, wf)`, `omi.main(argv=None) -> int`.

- [ ] **Step 1: Viết test luồng với GitHub giả `tests/test_cli_flow.py`**

```python
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import omi  # noqa: E402
import rules  # noqa: E402

WF = rules.load_workflow()
CFG = {}
FIELD_KEY = {"Status": "status", "Rework Count": "rework_count", "Blocked Reason": "blocked_reason"}


class FakeGh:
    """GitHub trong bộ nhớ, đủ cho các lệnh move/rework/block."""

    def __init__(self):
        self.issues, self.notes, self.assigned = {}, {}, []

    def add(self, n, type_, status, parent=None, state="OPEN", prs=(), body=""):
        self.issues[n] = {"number": n, "id": f"N{n}", "title": f"#{n}", "type": type_, "status": status,
                          "parent": parent, "state": state, "state_reason": None, "prs": list(prs),
                          "body": body, "rework_count": 0, "blocked_reason": None,
                          "open_blockers": 0, "milestone": "v1"}

    def issue_snapshot(self, cfg, n):
        s = dict(self.issues[n], item_id=f"I{n}")
        p = self.issues.get(s["parent"])
        s["parent"] = {"number": p["number"], "type": p["type"], "status": p["status"]} if p else None
        s["children"] = [{"number": c["number"], "type": c["type"], "status": c["status"], "state": c["state"]}
                         for c in self.issues.values() if c["parent"] == n]
        return s

    def set_field(self, cfg, item_id, field, value):
        self.issues[int(item_id[1:])][FIELD_KEY[field]] = value

    def clear_field(self, cfg, item_id, field):
        self.set_field(cfg, item_id, field, None)

    def comment(self, cfg, n, body):
        self.notes.setdefault(n, []).append(body)

    def comments(self, cfg, n):
        return self.notes.get(n, [])

    def close(self, cfg, n, reason):
        self.issues[n]["state"] = "CLOSED"

    def assign_self(self, cfg, n):
        self.assigned.append(n)


MERGED = [{"number": 99, "state": "MERGED", "merged": True}]


class TestFlow(unittest.TestCase):
    def setUp(self):
        self.real, self.g = omi.gh, FakeGh()
        omi.gh = self.g

    def tearDown(self):
        omi.gh = self.real

    def st(self, n):
        return self.g.issues[n]["status"]

    def test_first_task_start_rolls_up_chain(self):
        self.g.add(1, "Epic", "Approved")
        self.g.add(2, "User Story", "Approved", parent=1)
        self.g.add(3, "Task", "Ready", parent=2)
        omi.cmd_move(CFG, WF, 3, "In Progress")
        self.assertEqual((self.st(3), self.st(2), self.st(1)), ("In Progress", "In Progress", "In Progress"))
        self.assertEqual(self.g.assigned, [3])

    def test_last_task_done_moves_story_to_qa(self):
        self.g.add(1, "Epic", "In Progress")
        self.g.add(2, "User Story", "In Progress", parent=1)
        self.g.add(3, "Task", "In QA", parent=2, prs=MERGED)
        self.g.add(4, "Task", "Done", parent=2, state="CLOSED")
        omi.cmd_move(CFG, WF, 3, "Done")
        self.assertEqual((self.st(3), self.g.issues[3]["state"]), ("Done", "CLOSED"))
        self.assertEqual(self.st(2), "In QA")
        self.assertEqual(self.st(1), "In Progress")

    def test_move_idempotent_still_rolls_up(self):
        self.g.add(2, "User Story", "In Progress")
        self.g.add(3, "Task", "Done", parent=2, state="CLOSED")  # PR merge + built-in workflow đã set Done
        omi.cmd_move(CFG, WF, 3, "Done")
        self.assertEqual(self.st(2), "In QA")

    def test_story_done_closes_epic(self):
        self.g.add(1, "Epic", "In Progress")
        self.g.add(2, "User Story", "In QA", parent=1)
        omi.cmd_move(CFG, WF, 2, "Done")
        self.assertEqual(self.st(1), "Done")

    def test_guard_blocks_done_without_merged_pr(self):
        self.g.add(2, "User Story", "In Progress")
        self.g.add(3, "Task", "In QA", parent=2)
        with self.assertRaisesRegex(rules.RuleError, "chưa merge"):
            omi.cmd_move(CFG, WF, 3, "Done")
        self.assertEqual(self.st(3), "In QA")

    def test_rework_counts_and_comments(self):
        self.g.add(2, "User Story", "In Progress")
        self.g.add(3, "Task", "In Review", parent=2)
        self.assertEqual(omi.cmd_rework(CFG, WF, 3, "thiếu test"), "In Progress")
        self.assertEqual((self.st(3), self.g.issues[3]["rework_count"]), ("In Progress", 1))
        self.assertIn("omi:rework n=1 stage=review", self.g.notes[3][0])

    def test_rework_limit_blocks_then_unblock_returns_in_progress(self):
        self.g.add(2, "User Story", "In Progress")
        self.g.add(3, "Task", "In QA", parent=2)
        self.g.issues[3]["rework_count"] = 3
        self.assertEqual(omi.cmd_rework(CFG, WF, 3, "vẫn fail"), "Blocked")
        self.assertEqual(self.st(3), "Blocked")
        self.assertTrue(self.g.issues[3]["blocked_reason"])
        omi.cmd_unblock(CFG, WF, 3)
        self.assertEqual((self.st(3), self.g.issues[3]["blocked_reason"]), ("In Progress", None))

    def test_block_requires_reason(self):
        self.g.add(3, "Task", "Ready", parent=None)
        with self.assertRaisesRegex(rules.RuleError, "--reason"):
            omi.cmd_block(CFG, WF, 3)

    def test_cancel_requires_reason(self):
        self.g.add(3, "Task", "Ready")
        with self.assertRaisesRegex(rules.RuleError, "--reason"):
            omi.cmd_move(CFG, WF, 3, "Cancelled")

    def test_cr_done_writes_changelog_on_affected(self):
        self.g.add(1, "Epic", "In Progress")
        self.g.add(2, "User Story", "Done", parent=1, state="CLOSED")
        self.g.add(5, "Change Request", "In Progress", parent=1, body="x\n\n### Affects\n#2")
        self.g.add(6, "Task", "In QA", parent=5, prs=MERGED)
        omi.cmd_move(CFG, WF, 6, "Done")
        self.assertEqual(self.st(5), "Done")
        self.assertIn("Change Request #5", self.g.notes[2][-1])
        self.assertEqual(self.st(1), "Done")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Chạy để thấy thất bại** — Expected: `AttributeError: module 'omi' has no attribute 'cmd_move'`.

- [ ] **Step 3: Thêm vào `scripts/omi.py`**

```python
# ---------- điều phối ----------
def find_root(start=None):
    """Thư mục workspace chứa .omi/project.json, tìm từ start (mặc định cwd) lên trên."""
    p = Path(start or Path.cwd()).resolve()
    return next((d for d in (p, *p.parents) if (d / ".omi" / "project.json").exists()), None)


def load_cfg():
    """Cấu hình ở workspace (spec D12); trong CI repo không có .omi/ nên đọc biến OMI_CONFIG."""
    global TMP
    root = find_root()
    if root:
        cfg = json.loads((root / ".omi" / "project.json").read_text(encoding="utf-8"))
    elif os.environ.get("OMI_CONFIG"):
        root, cfg = Path.cwd(), json.loads(os.environ["OMI_CONFIG"])
        cfg["repo_dir"] = "."  # CI: cwd chính là repo
    else:
        raise RuleError("Không thấy .omi/project.json của workspace — chạy `OMI_CLI init --repo-dir <repo>` từ workspace")
    cfg["_root"] = str(root)
    TMP = root / ".omi" / "tmp"
    return cfg


def repo_dir(cfg):
    return Path(cfg.get("_root", ".")) / cfg.get("repo_dir", ".")


def snapshot(cfg, n):
    s = gh.issue_snapshot(cfg, n)
    if not s["item_id"]:
        raise RuleError(f"#{n} chưa có trong Project — chạy `audit --fix`")
    return s


def apply_status(cfg, wf, snap, target, reason=None):
    n = snap["number"]
    if target == rules.BLOCKED:
        gh.comment(cfg, n, f"<!-- omi:blocked-from={snap['status']} -->\n🚧 Blocked: {reason or 'xem blocked-by'}")
        if reason:
            gh.set_field(cfg, snap["item_id"], "Blocked Reason", reason)
    elif snap["status"] == rules.BLOCKED:
        gh.clear_field(cfg, snap["item_id"], "Blocked Reason")
        gh.comment(cfg, n, f"✅ Unblocked → {target}")
    elif reason:
        gh.comment(cfg, n, f"**{snap['status']} → {target}**: {reason}")
    gh.set_field(cfg, snap["item_id"], "Status", target)
    if rules.is_terminal(wf, target) and snap["state"] == "OPEN":
        gh.close(cfg, n, "completed" if target == "Done" else "not_planned")
        snap["state"] = "CLOSED"
    print(f"#{n} {snap['type']}: {snap['status']} → {target}")
    snap["status"] = target


def rollup_up(cfg, wf, snap, trigger):
    if not snap["parent"]:
        return
    p = snapshot(cfg, snap["parent"]["number"])
    new = rules.rollup(wf, p["type"], p["status"], [c["status"] for c in p["children"]], trigger)
    if not new:
        return
    apply_status(cfg, wf, p, new, f"Tự động (rollup từ #{snap['number']})")
    if p["type"] == "Change Request" and new == "Done":
        for a in affected(p["body"]):
            gh.comment(cfg, a, f"📝 Changelog: thay đổi theo Change Request #{p['number']} đã hoàn tất.")
    rollup_up(cfg, wf, p, new)


def cmd_new(cfg, wf, type_, title, parent=None, affects=(), milestone=None, priority=None,
            estimate=None, body="", key=None, status=None):
    psnap = gh.issue_snapshot(cfg, parent) if parent else None
    rules.check_parent(wf, type_, psnap["type"] if psnap else None)
    if milestone is None and psnap:
        milestone = psnap["milestone"]
    rules.check_links(wf, type_, len(affects), bool(milestone))
    status = status or wf["types"][type_]["initial"]
    if status not in rules.allowed_statuses(wf, type_):
        raise RuleError(f"{type_} không dùng status '{status}'")
    if priority and priority not in wf["priorities"]:
        raise RuleError(f"Priority phải là một trong {wf['priorities']}")
    tpl = rules.load_templates()
    title = rules.with_prefix(tpl, type_, title)  # prefix đầy đủ do script thêm, không cần người/LLM gõ
    full = build_body(body, affects, key)
    errs = rules.check_template(tpl, type_, title, full)
    if errs:
        raise RuleError(errs + [f"Xem khung: `template \"{type_}\"`"])
    for a in affects:
        gh.issue_db_id(cfg, a)  # GhError nếu không tồn tại
    issue = gh.create_issue(cfg, title, full, type_, milestone)
    if psnap:
        gh.add_sub_issue(cfg, parent, issue["id"])
    item = gh.add_to_project(cfg, issue["node_id"])
    gh.set_field(cfg, item, "Status", status)
    if priority:
        gh.set_field(cfg, item, "Priority", priority)
    if estimate is not None:
        gh.set_field(cfg, item, "Estimate", estimate)
    print(f"#{issue['number']} {type_} '{title}' → {status}")
    return issue["number"]


def cmd_move(cfg, wf, n, target, reason=None):
    snap = snapshot(cfg, n)
    if snap["status"] == target:
        # Built-in workflow của Project (Item closed / PR merged) có thể đã set Done trước: chỉ chạy rollup.
        print(f"#{n} đã ở '{target}', chỉ chạy rollup")
        rollup_up(cfg, wf, snap, target)
        return
    blocked_from = (find_marker(gh.comments(cfg, n), "blocked-from")
                    if snap["status"] == rules.BLOCKED else None)
    guards = rules.transition(wf, snap["type"], snap["status"], target, blocked_from)
    if "impact_analysis" in guards:
        snap["has_impact"] = find_marker(gh.comments(cfg, n), "impact") is not None
    errs = rules.evaluate_guards(guards, snap, reason)
    if errs:
        raise RuleError(errs)
    if target == "In Progress" and snap["status"] != rules.BLOCKED:
        gh.assign_self(cfg, n)
    apply_status(cfg, wf, snap, target, reason)
    rollup_up(cfg, wf, snap, target)


def cmd_rework(cfg, wf, n, reason):
    if not (reason and reason.strip()):
        raise RuleError("Cần --reason")
    snap = snapshot(cfg, n)
    stage = "review" if snap["status"] == "In Review" else "qa"
    target, count = rules.rework(wf, snap["type"], snap["status"], snap["rework_count"])
    gh.set_field(cfg, snap["item_id"], "Rework Count", count)
    gh.comment(cfg, n, f"<!-- omi:rework n={count} stage={stage} -->\n🔁 Rework lần {count} ({stage}): {reason}")
    apply_status(cfg, wf, snap, "In Progress")
    if target == rules.BLOCKED:
        apply_status(cfg, wf, snap, rules.BLOCKED,
                     f"Vượt giới hạn rework ({wf['max_rework']}), cần người xem")
    return target


def cmd_block(cfg, wf, n, reason=None, by=None):
    snap = snapshot(cfg, n)
    if by:
        gh.add_blocked_by(cfg, n, gh.issue_db_id(cfg, by))
        snap["open_blockers"] += 1
        reason = reason or f"blocked by #{by}"
    guards = rules.transition(wf, snap["type"], snap["status"], rules.BLOCKED)
    errs = rules.evaluate_guards(guards, snap, reason)
    if errs:
        raise RuleError(errs)
    apply_status(cfg, wf, snap, rules.BLOCKED, reason)


def cmd_unblock(cfg, wf, n):
    snap = snapshot(cfg, n)
    if snap["status"] != rules.BLOCKED:
        raise RuleError(f"#{n} không ở Blocked")
    prev = find_marker(gh.comments(cfg, n), "blocked-from")
    if not prev or prev is True:
        raise RuleError(f"#{n}: không tìm thấy marker blocked-from, dùng `move` với status mong muốn")
    cmd_move(cfg, wf, n, prev)


def cmd_tree(cfg, n=None):
    """Một truy vấn project_items rồi dựng cây cục bộ (không gọi API theo từng node)."""
    items = [i for i in gh.project_items(cfg) if i["title"] != gh.AUDIT_TITLE]
    by = {i["number"]: i for i in items}
    kids = {}
    for i in items:
        kids.setdefault(i["parent"], []).append(i)

    def walk(i, indent):
        print(f"{indent}#{i['number']} {i['title']} — {i['status']}")  # title đã có prefix loại
        for c in sorted(kids.get(i["number"], []), key=lambda x: x["number"]):
            walk(c, indent + "  ")

    if n is not None and n not in by:
        raise RuleError(f"#{n} không có trong Project")
    roots = [by[n]] if n is not None else sorted((i for i in items if i["parent"] not in by),
                                                 key=lambda x: x["number"])
    for r in roots:
        walk(r, "")


def cmd_next(cfg, wf):
    it = rules.pick_next(wf, gh.project_items(cfg))
    print(f"#{it['number']} {it['title']}" if it else "Không có Task/Bug nào Ready.")
    return it
```

- [ ] **Step 4: Thêm `main()` cuối `scripts/omi.py`** (các nhánh init/apply/audit/plan-show/context/start/check/submit/qa/accept/impact gọi hàm định nghĩa ở Task 011–015; Python chỉ phân giải tên lúc gọi nên test hiện tại không bị ảnh hưởng)

```python
def _num(s):
    return int(str(s).lstrip("#"))


def _nums(s):
    return [_num(x) for x in s.split(",") if x.strip()]


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(prog="omi")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init")
    p.add_argument("--milestone")
    p.add_argument("--from-template", type=int)
    p.add_argument("--template-only", action="store_true")
    p.add_argument("--hub-repo", default="omi-home/omi-hub")
    p.add_argument("--test-cmd")
    p.add_argument("--lint-cmd")
    p.add_argument("--accept-cmd")
    p.add_argument("--repo-dir", default=".", help="repo git, tương đối với workspace (cwd)")
    p = sub.add_parser("new")
    p.add_argument("type")
    p.add_argument("title")
    p.add_argument("--parent", type=_num)
    p.add_argument("--affects", type=_nums, default=[])
    p.add_argument("--milestone")
    p.add_argument("--priority")
    p.add_argument("--estimate", type=float)
    p.add_argument("--body-file")
    p.add_argument("--field", action="append", default=[], help='"Tên mục=nội dung", lặp lại được')
    p = sub.add_parser("move")
    p.add_argument("number", type=_num)
    p.add_argument("status")
    p.add_argument("--reason")
    p = sub.add_parser("rework")
    p.add_argument("number", type=_num)
    p.add_argument("--reason", required=True)
    p = sub.add_parser("block")
    p.add_argument("number", type=_num)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--reason")
    g.add_argument("--by", type=_num)
    p = sub.add_parser("unblock")
    p.add_argument("number", type=_num)
    p = sub.add_parser("tree")
    p.add_argument("number", type=_num, nargs="?")
    sub.add_parser("next")
    p = sub.add_parser("apply")
    p.add_argument("plan")
    p.add_argument("--approve", action="store_true")
    p = sub.add_parser("audit")
    p.add_argument("--fix", action="store_true")
    p = sub.add_parser("plan-show")
    p.add_argument("plan")
    p = sub.add_parser("template")
    p.add_argument("type")
    for name in ("context", "submit", "qa", "accept", "pr-lint"):
        sub.add_parser(name).add_argument("number", type=_num)
    p = sub.add_parser("start")
    p.add_argument("number", type=_num, nargs="?")
    sub.add_parser("check")
    p = sub.add_parser("impact")
    p.add_argument("number", type=_num)
    p.add_argument("--post", action="store_true")
    p = sub.add_parser("status")
    p.add_argument("--milestone")
    sub.add_parser("resume")
    p = sub.add_parser("review-done")
    p.add_argument("number", type=_num)
    p.add_argument("--fail", help="tóm tắt blocker; có thì script rework")
    a = ap.parse_args(argv)
    wf = rules.load_workflow()
    try:
        if a.cmd == "init":
            cmd_init(wf, a.milestone, a.from_template, a.template_only, a.hub_repo,
                     a.test_cmd, a.lint_cmd, a.accept_cmd, a.repo_dir)
            return 0
        if a.cmd == "plan-show":
            return cmd_plan_show(wf, a.plan)
        if a.cmd == "template":
            print(rules.skeleton(rules.load_templates(), a.type))
            return 0
        cfg = load_cfg()
        if a.cmd in ("check", "qa", "accept", "pr-lint"):
            return {"check": lambda: cmd_check(cfg), "qa": lambda: cmd_qa(cfg, wf, a.number),
                    "accept": lambda: cmd_accept(cfg, wf, a.number),
                    "pr-lint": lambda: cmd_pr_lint(cfg, a.number)}[a.cmd]()
        if a.cmd == "context":
            cmd_context(cfg, a.number)
        elif a.cmd == "start":
            cmd_start(cfg, wf, a.number)
        elif a.cmd == "submit":
            cmd_submit(cfg, wf, a.number)
        elif a.cmd == "impact":
            cmd_impact(cfg, a.number, a.post)
        elif a.cmd == "status":
            cmd_status(cfg, wf, a.milestone)
        elif a.cmd == "resume":
            cmd_resume(cfg, wf)
        elif a.cmd == "review-done":
            cmd_review_done(cfg, wf, a.number, a.fail)
        elif a.cmd == "new":
            body = (Path(a.body_file).read_text(encoding="utf-8") if a.body_file else
                    rules.fill(rules.load_templates(), a.type, dict(f.split("=", 1) for f in a.field)))
            cmd_new(cfg, wf, a.type, a.title, a.parent, a.affects, a.milestone, a.priority, a.estimate, body)
        elif a.cmd == "move":
            cmd_move(cfg, wf, a.number, a.status, a.reason)
        elif a.cmd == "rework":
            cmd_rework(cfg, wf, a.number, a.reason)
        elif a.cmd == "block":
            cmd_block(cfg, wf, a.number, a.reason, a.by)
        elif a.cmd == "unblock":
            cmd_unblock(cfg, wf, a.number)
        elif a.cmd == "tree":
            cmd_tree(cfg, a.number)
        elif a.cmd == "next":
            cmd_next(cfg, wf)
        elif a.cmd == "apply":
            cmd_apply(cfg, wf, a.plan, a.approve)
        elif a.cmd == "audit":
            return cmd_audit(cfg, wf, a.fix)
        return 0
    except (RuleError, gh.GhError) as e:
        print(f"❌ {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Chạy test** — Run: `python -m unittest discover -s tests -v` — Expected: PASS.

- [ ] **Step 6: Commit** — `git add -A && git commit -m "feat(cli): new/move/rework/block/unblock/tree/next + rollup"`

### Task 011: `init` + templates cho repo đích

**Files:**
- Modify: `scripts/omi.py` (thêm `write_templates`, `cmd_init` trước `main`)
- Create: `templates/AGENTS.md`, `templates/ISSUE_TEMPLATE/config.yml`, `templates/workflows/omi-audit.yml`, `docs/views.md`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `gh` bootstrap (Task 008), `merge_agents_md` (Task 009), `rules.load_templates` (Task 006).
- Produces: `omi.render_form(type_, t) -> str`, `omi.form_filename(type_) -> str`, `omi.render_pr_template(pr_tpl) -> str`, `omi.write_templates(hub_repo: str, repo: Path, workspace: Path) -> None`, `omi.cmd_init(wf, milestone=None, from_template=None, template_only=False, hub_repo="omi-home/omi-hub", test_cmd=None, lint_cmd=None, accept_cmd=None, repo_dir_=".") -> None`. Repo nhận: `.github/ISSUE_TEMPLATE/*.yml`, `.github/pull_request_template.md`, `.github/workflows/omi-audit.yml`. Workspace nhận: `AGENTS.md`, `.omi/project.json` (gồm `repo_dir`, `commands`, `security_paths`, `review_max_diff_lines`, `default_branch`). Repo variable `OMI_CONFIG` = nội dung config (cho Action).

- [ ] **Step 1: Thêm test vào `tests/test_cli.py`**

```python
import os  # các import này đặt cùng nhóm import ở đầu file
import tempfile
from unittest import mock


class TestConfig(unittest.TestCase):
    def test_find_root_walks_up_and_repo_dir(self):
        with tempfile.TemporaryDirectory() as d:
            ws = Path(d)
            (ws / ".omi").mkdir()
            (ws / ".omi" / "project.json").write_text('{"repo_dir": "app"}', encoding="utf-8")
            (ws / "app" / "src").mkdir(parents=True)
            self.assertEqual(omi.find_root(ws / "app" / "src"), ws.resolve())
            old = os.getcwd()
            os.chdir(ws / "app" / "src")
            try:
                cfg = omi.load_cfg()
            finally:
                os.chdir(old)
            self.assertEqual(omi.repo_dir(cfg).resolve(), (ws / "app").resolve())
            self.assertEqual(omi.TMP, ws.resolve() / ".omi" / "tmp")

    def test_env_fallback_in_ci(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"OMI_CONFIG": '{"owner": "o"}'}):
            old = os.getcwd()
            os.chdir(d)
            try:
                cfg = omi.load_cfg()
            finally:
                os.chdir(old)
            self.assertEqual((cfg["owner"], cfg["repo_dir"]), ("o", "."))


class TestWriteTemplates(unittest.TestCase):
    def test_writes_and_merges(self):
        with tempfile.TemporaryDirectory() as d:
            ws = Path(d)
            dest = ws / "app"  # repo là thư mục con của workspace
            dest.mkdir()
            (ws / "AGENTS.md").write_text("# Dự án X\n", encoding="utf-8")
            omi.write_templates("acme/omi-hub", dest, ws)
            omi.write_templates("acme/omi-hub", dest, ws)  # chạy lại không nhân đôi
            agents = (ws / "AGENTS.md").read_text(encoding="utf-8")
            self.assertFalse((dest / "AGENTS.md").exists())
            self.assertFalse((dest / ".omi").exists())
            self.assertTrue(agents.startswith("# Dự án X"))
            self.assertEqual(agents.count(omi.BEGIN), 1)
            forms = sorted(p.name for p in (dest / ".github/ISSUE_TEMPLATE").glob("*.yml"))
            self.assertEqual(forms, ["bug.yml", "change-request.yml", "config.yml", "epic.yml",
                                     "functional-requirement.yml", "non-functional-requirement.yml",
                                     "task.yml", "user-story.yml"])
            wf = (dest / ".github/workflows/omi-audit.yml").read_text(encoding="utf-8")
            self.assertIn("repository: acme/omi-hub", wf)
            self.assertNotIn("__OMI_HUB_REPO__", wf)
            pr_md = (dest / ".github/pull_request_template.md").read_text(encoding="utf-8")
            self.assertIn("### Liên kết", pr_md)
            self.assertIn("### Security", pr_md)
            self.assertLessEqual(len(agents.splitlines()), 20)  # giữ AGENTS.md ngắn: nạp vào mọi phiên

    def test_render_form(self):
        tpl = omi.rules.load_templates()
        nfr = omi.render_form("Non-Functional Requirement", tpl["Non-Functional Requirement"])
        self.assertIn('type: "Non-Functional Requirement"', nfr)
        self.assertIn("type: dropdown", nfr)
        self.assertIn('label: "Cách đo"', nfr)
        self.assertIn('title: "[Functional Requirement] Hệ thống phải "', omi.render_form("Functional Requirement", tpl["Functional Requirement"]))
        self.assertIn('title: "[Epic] "', omi.render_form("Epic", tpl["Epic"]))
        self.assertIn("type: input", omi.render_form("Bug", tpl["Bug"]))
        self.assertEqual(omi.form_filename("User Story"), "user-story.yml")
```

- [ ] **Step 2: Chạy để thấy thất bại** — Expected: `AttributeError ... 'write_templates'`.

- [ ] **Step 3: Viết `templates/AGENTS.md`**

Ngắn có chủ đích (nạp vào mọi phiên); luật chi tiết nằm trong CLI, CLI từ chối thao tác sai và in lý do.

```markdown
<!-- omi:begin -->
## omi-hub
Dự án quản lý bằng omi-hub (GitHub Project). `OMI_CLI` = lệnh ở dòng `OMI_CLI:` đầu phiên. CLI tự kiểm luật và in lý do khi từ chối.
- **Script-first (ưu tiên hàng đầu với mọi yêu cầu):** trước tiên tìm lệnh `OMI_CLI`/script làm được; LLM chỉ làm việc cần phán đoán; việc lặp lại chưa có script → đề xuất viết script trước.
- Đổi status chỉ qua `OMI_CLI move|rework|block|unblock` (không `gh issue close`, `gh project item-edit`).
- `Approved` chỉ khi người dùng xác nhận.
- Lỗi khi đang làm → `rework`; lỗi trên item đã Done → `new Bug --affects`; đổi yêu cầu đã Approved → skill omi-change.
- Test nghiệm thu: AC thứ i của issue #p ↔ test có tên chứa `ac<p>_<i>`; AC không tự động hóa được ghi `[manual]`.
- Mỗi loại có template chuẩn: title có prefix đầy đủ (`[Functional Requirement] ...`, CLI tự thêm) + body theo `OMI_CLI template <type>`; tạo nhanh bằng `new ... --field "Mục=nội dung"`. PR do `submit` sinh theo template PR. CLI từ chối sai mẫu.
- Làm task: skill omi-implement. Lập backlog từ PRD: skill omi-plan.
- Lệnh: next · tree [n] · context n · start [n] · check · submit n · qa n · accept n · new · move · rework · block · unblock · impact · audit
<!-- omi:end -->
```

- [ ] **Step 4: Issue forms sinh từ `templates.json`** (không viết tay từng form, để forms và CLI không bao giờ lệch nhau)

`templates/ISSUE_TEMPLATE/config.yml` (file tĩnh duy nhất):
```yaml
blank_issues_enabled: false
```

Thêm vào `scripts/omi.py` (nhóm helper thuần, sau `merge_agents_md`):

```python
def _q(s):
    return json.dumps(s, ensure_ascii=False)  # chuỗi/list JSON là scalar/flow YAML hợp lệ


def form_filename(type_):
    return type_.lower().replace(" ", "-") + ".yml"


def render_form(type_, t):
    lines = [f"name: {_q(type_)}", f"description: {_q(t['title']['hint'])}", f"type: {_q(type_)}"]
    lines.append(f"title: {_q(rules.prefix(type_) + t['title'].get('prefill', ''))}")
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
```

Label của form chính là heading `### <label>` mà GitHub render vào body, nên issue tạo từ web đi qua được `check_template`.

- [ ] **Step 5: Viết `templates/workflows/omi-audit.yml`**

```yaml
name: omi-audit
on:
  issues:
    types: [opened, edited, closed, reopened, typed, untyped, milestoned, demilestoned]
  pull_request:
    types: [opened, edited, synchronize, reopened, closed]
  schedule:
    - cron: "0 2 * * *"
  workflow_dispatch:
concurrency:  # audit quét toàn bộ nên run mới thay run cũ; pr-lint tách nhóm theo PR
  group: omi-${{ github.event_name == 'pull_request' && format('pr-{0}', github.event.pull_request.number) || 'audit' }}
  cancel-in-progress: true
jobs:
  audit:
    if: >-
      (github.event_name != 'pull_request' || github.event.action == 'closed') &&
      (github.event_name != 'issues' || github.event.issue.title != 'OMI Audit')
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/checkout@v4
        with:
          repository: __OMI_HUB_REPO__
          path: .omi-hub
          token: ${{ secrets.OMI_PROJECT_TOKEN }}
      - run: python .omi-hub/scripts/omi.py audit --fix
        env:
          GH_TOKEN: ${{ secrets.OMI_PROJECT_TOKEN }}
          OMI_CONFIG: ${{ vars.OMI_CONFIG }}
  pr-lint:
    if: github.event_name == 'pull_request' && github.event.action != 'closed'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/checkout@v4
        with:
          repository: __OMI_HUB_REPO__
          path: .omi-hub
          token: ${{ secrets.OMI_PROJECT_TOKEN }}
      - run: python .omi-hub/scripts/omi.py pr-lint ${{ github.event.pull_request.number }}
        env:
          GH_TOKEN: ${{ secrets.OMI_PROJECT_TOKEN }}
          OMI_CONFIG: ${{ vars.OMI_CONFIG }}
```

- [ ] **Step 6: Viết `docs/views.md`**

```markdown
# Tạo 5 view cho Project mẫu (làm một lần cho mỗi org)

API GitHub chưa cho tạo view, nên tạo tay trong Project "OMI Template" (sau `omi init --template-only`):

| View | Layout | Cấu hình |
|---|---|---|
| Board | Board | Column by: Status. Filter: `-status:Done,Cancelled` |
| Hierarchy | Table | Group by: Parent issue. Hiện cột: Type, Status, Sub-issues progress, Milestone |
| Requirements | Table | Filter: `type:"User Story","Functional Requirement","Non-Functional Requirement","Change Request"`. Group by: Status |
| Delivery | Table | Filter: `type:Task,Bug`. Group by: Milestone. Sort: Priority |
| Blocked & Rework | Table | Filter: `status:Blocked` (tạo thêm view phụ `rework-count:>0` nếu muốn) |

Workflows (Project → ⋯ → Workflows):
- Bật "Auto-add to project" cho repo, filter `is:issue`.
- Tắt "Item closed" và "Pull request merged" (omi tự quản Done/Cancelled).

Sau đó dự án mới dùng: `OMI_CLI init` với `--from-template <số project mẫu>`.
```

- [ ] **Step 7: Thêm `write_templates` và `cmd_init` vào `scripts/omi.py` (trước `def _num`)**

```python
def write_templates(hub_repo, repo=Path("."), workspace=Path(".")):
    """Repo chỉ nhận `.github/` (GitHub bắt buộc nằm trong repo); AGENTS.md ghi ra workspace (spec D12)."""
    forms = repo / ".github" / "ISSUE_TEMPLATE"
    forms.mkdir(parents=True, exist_ok=True)
    (forms / "config.yml").write_text((TEMPLATES / "ISSUE_TEMPLATE" / "config.yml").read_text(encoding="utf-8"),
                                      encoding="utf-8")
    for type_, t in rules.load_templates().items():
        (forms / form_filename(type_)).write_text(render_form(type_, t), encoding="utf-8")
    (repo / ".github" / "pull_request_template.md").write_text(render_pr_template(rules.load_pr_template()),
                                                                encoding="utf-8")
    wfdir = repo / ".github" / "workflows"
    wfdir.mkdir(parents=True, exist_ok=True)
    audit = (TEMPLATES / "workflows" / "omi-audit.yml").read_text(encoding="utf-8")
    (wfdir / "omi-audit.yml").write_text(audit.replace("__OMI_HUB_REPO__", hub_repo), encoding="utf-8")
    agents = workspace / "AGENTS.md"
    old = agents.read_text(encoding="utf-8") if agents.exists() else ""
    agents.write_text(merge_agents_md(old, (TEMPLATES / "AGENTS.md").read_text(encoding="utf-8")),
                      encoding="utf-8")


def cmd_init(wf, milestone=None, from_template=None, template_only=False, hub_repo="omi-home/omi-hub",
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
```

- [ ] **Step 8: Chạy test** — Expected: PASS.

- [ ] **Step 9: Thử thật trên sandbox** (từ workspace chứa clone `omi-sandbox`)

```bash
# chạy từ thư mục workspace, clone sandbox nằm ở ./omi-sandbox
python <omi-hub>/scripts/omi.py init --repo-dir omi-sandbox --milestone "v0.1" --test-cmd "python -m unittest" --accept-cmd "python -m unittest -k ac{n}_ -v"
cat .omi/project.json && ls omi-sandbox/.github && test ! -e omi-sandbox/AGENTS.md
python <omi-hub>/scripts/omi.py init --repo-dir omi-sandbox --milestone "v0.1"   # chạy lại: không tạo trùng
gh variable get OMI_CONFIG -R omi-home/omi-sandbox | head -c 80
```
Expected: lần 2 không lỗi, cùng `project_number`; `gh project field-list` có đủ 10 Status + 4 field.

- [ ] **Step 10: Commit** — `git add -A && git commit -m "feat(init): bootstrap repo + templates"`

### Task 012: `apply` plan

**Files:**
- Modify: `scripts/omi.py` (thêm `cmd_apply` trước `def _num`)
- Test: `tests/test_cli_flow.py`

**Interfaces:**
- Consumes: `rules.validate_plan`, `cmd_new`, `gh.existing_keys`.
- Produces: `omi.cmd_apply(cfg, wf, plan_path, approve=False) -> dict[str, int]` (key → số issue). Định dạng plan:

```json
{"milestone": "v1.0", "items": [
  {"key": "E001", "type": "Epic", "title": "...", "body": "...", "priority": "P1", "children": [
    {"key": "E001.S001", "type": "User Story", "title": "...", "body": "...### Acceptance criteria\n- [ ] ...",
     "estimate": 3, "children": [{"key": "E001.S001.T001", "type": "Task", "title": "..."}]}]},
  {"key": "T001", "type": "Task", "title": "...", "parent": 42}
]}
```

- [ ] **Step 1: Thêm test vào `tests/test_cli_flow.py`**

```python
import json
import tempfile
from unittest import mock


class TestApply(unittest.TestCase):
    PLAN = {"milestone": "v1", "items": [
        {"key": "E001", "type": "Epic", "title": "Quản lý đơn hàng",
         "body": "### Mục tiêu\nBán hàng online\n\n### Phạm vi\n- đặt hàng", "children": [
            {"key": "E001.S001", "type": "User Story", "title": "Khách hàng có thể đặt hàng",
             "body": "### Story\nLà khách, tôi muốn đặt hàng để mua nhanh.\n\n### Acceptance criteria\n- [ ] a",
             "children": [{"key": "E001.S001.T001", "type": "Task", "title": "Thêm API đặt hàng",
                           "body": "### Việc cần làm\nPOST /orders\n\n### Definition of done\n- [ ] Test pass"}]}]}]}

    def run_apply(self, existing, approve):
        calls = []

        def fake_new(cfg, wf, type_, title, parent=None, **kw):
            calls.append((type_, parent, kw.get("status"), kw.get("key"), kw.get("milestone")))
            return 100 + len(calls)

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(self.PLAN, f)
        with mock.patch.object(omi, "cmd_new", fake_new), \
                mock.patch.object(omi.gh, "existing_keys", return_value=existing):
            keys = omi.cmd_apply({}, WF, f.name, approve)
        Path(f.name).unlink()
        return calls, keys

    def test_creates_parent_first_with_approved_statuses(self):
        calls, keys = self.run_apply({}, approve=True)
        self.assertEqual(calls, [("Epic", None, "Approved", "E001", "v1"),
                                 ("User Story", 101, "Approved", "E001.S001", None),
                                 ("Task", 102, "Ready", "E001.S001.T001", None)])
        self.assertEqual(keys, {"E001": 101, "E001.S001": 102, "E001.S001.T001": 103})

    def test_idempotent_and_draft_without_approve(self):
        calls, keys = self.run_apply({"E001": 7}, approve=False)
        self.assertEqual(calls, [("User Story", 7, None, "E001.S001", None), ("Task", 101, None, "E001.S001.T001", None)])
        self.assertEqual(keys["E001"], 7)

    def test_invalid_plan_rejected(self):
        bad = {"items": [{"key": "T001", "type": "Task", "title": "x"}]}
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(bad, f)
        with self.assertRaisesRegex(rules.RuleError, "bắt buộc có parent"):
            omi.cmd_apply({}, WF, f.name)
        Path(f.name).unlink()
```

`TestApply` không cần `FakeGh` vì đã patch `cmd_new` và `existing_keys`.

- [ ] **Step 2: Chạy để thấy thất bại** — Expected: `AttributeError ... 'cmd_apply'`.

- [ ] **Step 3: Thêm vào `scripts/omi.py`**

```python
APPROVE_STATUS = {"Epic": "Approved", "User Story": "Approved", "Functional Requirement": "Approved", "Non-Functional Requirement": "Approved",
                  "Task": "Ready"}


def cmd_apply(cfg, wf, plan_path, approve=False):
    plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    errs = rules.validate_plan(wf, plan, rules.load_templates())
    if errs:
        raise RuleError(errs)
    keys = dict(gh.existing_keys(cfg))

    def create(node, parent):
        n = keys.get(node["key"])
        if n is None:
            top = parent is None
            n = cmd_new(cfg, wf, node["type"], node["title"], parent=parent,
                        affects=node.get("affects", []),
                        milestone=(node.get("milestone") or plan.get("milestone")) if top else None,
                        priority=node.get("priority"), estimate=node.get("estimate"),
                        body=node.get("body", ""), key=node["key"],
                        status=APPROVE_STATUS.get(node["type"]) if approve else None)
            keys[node["key"]] = n
        for c in node.get("children", []):
            create(c, n)

    for node in plan["items"]:
        create(node, node.get("parent"))
    return keys
```

- [ ] **Step 4: Chạy test** — Expected: PASS.
- [ ] **Step 5: Commit** — `git commit -am "feat(cli): apply plan idempotent"`

### Task 013: `audit`

**Files:**
- Modify: `scripts/omi.py` (thêm `apply_fix`, `cmd_audit` trước `def _num`)
- Test: `tests/test_cli_flow.py`

**Interfaces:**
- Consumes: `rules.check_invariants`, `gh.project_items`, `gh.repo_issues`, `gh.issue_snapshot`, `gh.upsert_audit_issue`, `gh.add_to_project`, `gh.set_field`, `gh.close`, `gh.set_milestone`.
- Produces: `omi.apply_fix(cfg, item, fix)`, `omi.cmd_audit(cfg, wf, fix=False) -> int` (0 sạch hoặc đã sửa hết, 1 còn vấn đề).

- [ ] **Step 1: Thêm test**

```python
class TestAudit(unittest.TestCase):
    def test_fixes_and_reports(self):
        items = [
            {"item_id": "I1", "id": "N1", "number": 1, "title": "e", "type": "Epic", "state": "OPEN",
             "state_reason": None, "status": "Done", "priority": None, "blocked_reason": None,
             "milestone": "v1", "milestone_due": None, "parent": None, "open_blockers": 0, "in_project": True},
            {"item_id": "I2", "id": "N2", "number": 2, "title": "t", "type": "Task", "state": "OPEN",
             "state_reason": None, "status": "Blocked", "priority": None, "blocked_reason": None,
             "milestone": "v1", "milestone_due": None, "parent": None, "open_blockers": 0, "in_project": True},
        ]
        g = mock.Mock()
        g.AUDIT_TITLE = "OMI Audit"
        g.project_items.return_value = items
        g.repo_issues.return_value = [{"number": 1, "title": "e", "state": "OPEN"},
                                      {"number": 2, "title": "t", "state": "OPEN"},
                                      {"number": 3, "title": "OMI Audit", "state": "OPEN"}]
        real, omi.gh = omi.gh, g
        try:
            code = omi.cmd_audit({}, WF, fix=True)
        finally:
            omi.gh = real
        g.close.assert_called_once_with({}, 1, "completed")
        body = g.upsert_audit_issue.call_args.args[1]
        self.assertIn("#2", body)            # Task thiếu parent + Blocked không lý do
        self.assertIn("[x] #1", body)        # Epic đã tự sửa
        self.assertEqual(code, 1)
```

- [ ] **Step 2: Chạy để thấy thất bại** — Expected: `AttributeError ... 'cmd_audit'`.

- [ ] **Step 3: Thêm vào `scripts/omi.py`**

```python
def apply_fix(cfg, item, fix):
    kind, val = fix
    if kind == "add":
        gh.set_field(cfg, gh.add_to_project(cfg, item["id"]), "Status", val)
    elif kind == "status":
        gh.set_field(cfg, item["item_id"], "Status", val)
    elif kind == "close":
        gh.close(cfg, item["number"], "completed" if val == "Done" else "not_planned")
    elif kind == "milestone":
        gh.set_milestone(cfg, item["number"], val)


def cmd_audit(cfg, wf, fix=False):
    items = [i for i in gh.project_items(cfg) if i["title"] != gh.AUDIT_TITLE]
    by = {i["number"]: i for i in items}
    for i in gh.repo_issues(cfg):
        if i["number"] not in by and i["title"] != gh.AUDIT_TITLE:
            s = gh.issue_snapshot(cfg, i["number"])
            items.append({"number": s["number"], "id": s["id"], "type": s["type"], "in_project": False})
    lines, unfixed = [], 0
    for it in items:
        for p in rules.check_invariants(wf, it, by):
            done = bool(fix and p["fix"])
            if done:
                apply_fix(cfg, it, p["fix"])
            unfixed += not done
            lines.append(f"- [{'x' if done else ' '}] #{p['number']}: {p['problem']}"
                         + (" (đã tự sửa)" if done else ""))
    gh.upsert_audit_issue(cfg, "\n".join(lines) if unfixed else None)
    print("\n".join(lines) or "✅ Audit sạch")
    return 1 if unfixed else 0
```

- [ ] **Step 4: Chạy test** — Expected: PASS.

- [ ] **Step 5: Thử thật trên sandbox**: trên web đóng tay một issue đang `Ready` → `python <omi-hub>/scripts/omi.py audit --fix` → Expected: Status chuyển Done/Cancelled theo lý do đóng, issue "OMI Audit" được cập nhật hoặc đóng.

- [ ] **Step 6: Commit** — `git commit -am "feat(cli): audit bất biến + tự sửa"`

### Task 014: Helper thuần cho pipeline (AC, nghiệm thu, security, context, plan)

**Files:**
- Modify: `scripts/omi.py` (thêm sau nhóm helper thuần của Task 009)
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `MARKER`, `DEFAULT_SECURITY` (Task 009/011 đầu file), `rules.AC_TYPES`.
- Produces: `omi.tail(text, n=60) -> str`, `omi.ac_section(body) -> str`, `omi.parse_ac(body) -> list[{"i": int, "text": str, "checked": bool, "manual": bool}]`, `omi.accept_verdict(n, acs, output, exit_code) -> tuple[bool, list[str]]`, `omi.needs_security(files: list[str], labels: list[str], parent: dict|None = None, patterns=DEFAULT_SECURITY) -> bool`, `omi.strip_markers(body) -> str`, `omi.render_context(s, parent=None, affects=()) -> str`, `omi.render_plan(plan) -> str`, `omi.pr_title(s) -> str`, `omi.render_pr_body(s, parent, commits: list[str], security: bool) -> str`.

- [ ] **Step 1: Thêm test vào `tests/test_cli.py`**

```python
STORY_BODY = ("Là dev...\n\n### Acceptance criteria\n- [ ] đăng nhập được\n- [x] [manual] UI đúng mockup\n"
              "\n### Ghi chú\n- [ ] không tính")


class TestPipelineHelpers(unittest.TestCase):
    def test_parse_ac(self):
        acs = omi.parse_ac(STORY_BODY)
        self.assertEqual([(a["i"], a["manual"], a["checked"]) for a in acs], [(1, False, False), (2, True, True)])
        self.assertEqual(omi.parse_ac("không có mục"), [])

    def test_accept_verdict(self):
        acs = omi.parse_ac(STORY_BODY)
        self.assertEqual(omi.accept_verdict(12, acs, "test_ac12_1 ... ok", 0), (True, []))
        ok, missing = omi.accept_verdict(12, acs, "test_other ok", 0)
        self.assertFalse(ok)
        self.assertIn("ac12_1", missing[0])
        self.assertFalse(omi.accept_verdict(12, acs, "test_ac12_1 FAIL", 1)[0])
        unticked = omi.parse_ac("### Acceptance criteria\n- [ ] [manual] UI")
        self.assertEqual(omi.accept_verdict(5, unticked, "", 0), (False, ["AC1 [manual] chưa tick"]))

    def test_needs_security(self):
        self.assertTrue(omi.needs_security(["README.md"], ["Security"]))
        self.assertTrue(omi.needs_security(["src/auth/login.py"], []))
        self.assertFalse(omi.needs_security(["README.md", "src/ui/button.tsx"], []))
        nfr = {"type": "Non-Functional Requirement", "body": "### Nhóm\n\nSecurity\n\n### Chỉ số và ngưỡng\n..."}
        self.assertTrue(omi.needs_security(["README.md"], [], nfr))

    def test_tail(self):
        text = "\n".join(str(i) for i in range(100))
        self.assertEqual(omi.tail(text).splitlines(), [str(i) for i in range(40, 100)])

    def test_render_context(self):
        s = {"number": 7, "type": "Task", "title": "[Task] Làm login", "status": "In Progress",
             "body": "Chi tiết\n\n<!-- omi:key=E001.S001.T001 -->"}
        parent = {"number": 10, "type": "User Story", "title": "[User Story] Khách có thể đăng nhập", "body": STORY_BODY}
        text = omi.render_context(s, parent)
        self.assertIn("# #7 [Task] Làm login — In Progress", text)
        self.assertIn("đăng nhập được", text)
        self.assertIn("ac10_", text)
        self.assertNotIn("omi:key", text)
        self.assertNotIn("không tính", text)

    def test_render_plan(self):
        plan = {"items": [{"key": "E001", "type": "Epic", "title": "E", "children": [
            {"key": "E001.S001", "type": "User Story", "title": "S", "body": STORY_BODY}]}]}
        self.assertEqual(omi.render_plan(plan), "E001 [Epic] E\n  E001.S001 [User Story] S (AC:2)")

    def test_pr_body_passes_pr_template(self):
        s = {"number": 7, "title": "[Task] Làm form đăng nhập", "body": ""}
        parent = {"number": 10, "type": "User Story", "title": "[User Story] Khách có thể đăng nhập", "body": STORY_BODY}
        body = omi.render_pr_body(s, parent, ["#7: thêm form login"], True)
        pr_tpl = omi.rules.load_pr_template()
        self.assertEqual(omi.rules.check_pr(pr_tpl, omi.pr_title(s), body), [])
        self.assertIn("ac10_1", body)
        self.assertNotIn("ac10_2", body)  # AC [manual] không có test
        self.assertIn("Có chạm security", body)

    def test_pr_template_md_must_be_filled(self):
        pr_tpl = omi.rules.load_pr_template()
        errs = omi.rules.check_pr(pr_tpl, "[Task] Làm form đăng nhập (#7)", omi.render_pr_template(pr_tpl))
        self.assertTrue(any("Liên kết" in e for e in errs))
        self.assertTrue(any("Security" in e for e in errs))
```

- [ ] **Step 2: Chạy để thấy thất bại** — Expected: `AttributeError ... 'parse_ac'`.

- [ ] **Step 3: Thêm vào `scripts/omi.py`**

```python
def tail(text, n=60):
    return "\n".join((text or "").rstrip().splitlines()[-n:])


def ac_section(body):
    m = re.search(r"^### Acceptance criteria\s*\n(.*?)(?=^### |\Z)", body or "", re.M | re.S)
    return m.group(1).strip() if m else ""


def parse_ac(body):
    out = []
    for line in ac_section(body).splitlines():
        m = re.match(r"\s*- \[( |x|X)\]\s*(.+)", line)
        if m:
            out.append({"i": len(out) + 1, "text": m.group(2).strip(), "checked": m.group(1) != " ",
                        "manual": "[manual]" in m.group(2).lower()})
    return out


def accept_verdict(n, acs, output, exit_code):
    """AC tự động cần test `ac<n>_<i>` xuất hiện trong output và lệnh thoát 0; AC [manual] cần được tick."""
    missing = []
    for a in acs:
        if a["manual"]:
            if not a["checked"]:
                missing.append(f"AC{a['i']} [manual] chưa tick")
        elif exit_code != 0 or f"ac{n}_{a['i']}" not in output:
            missing.append(f"AC{a['i']} thiếu hoặc fail test ac{n}_{a['i']}")
    return not missing, missing


def needs_security(files, labels, parent=None, patterns=DEFAULT_SECURITY):
    if any(lb.lower() == "security" for lb in labels):
        return True
    if parent and parent.get("type") == "Non-Functional Requirement" and re.search(r"### Nhóm\s+Security", parent.get("body") or ""):
        return True
    rx = re.compile("|".join(patterns), re.I)
    return any(rx.search(f) for f in files)


def strip_markers(body):
    return MARKER.sub("", body or "").strip()


def render_context(s, parent=None, affects=()):
    out = [f"# #{s['number']} {s['title']} — {s['status']}", strip_markers(s["body"])]
    for label, x in ([("Parent", parent)] if parent else []) + [("Affects", a) for a in affects]:
        out += [f"## {label} #{x['number']} {x['title']}",
                "### Acceptance criteria\n" + (ac_section(x["body"]) or "(không có)")]
    if parent and parent["type"] in rules.AC_TYPES:
        p = parent["number"]
        out.append(f"## Quy ước\nAC thứ i của #{p} (trừ [manual]) ↔ test có tên chứa `ac{p}_<i>`. Kiểm tra: `check`.")
    return "\n\n".join(x for x in out if x)


def render_plan(plan):
    lines = []

    def walk(node, depth):
        ac = f" (AC:{len(parse_ac(node.get('body', '')))})" if node["type"] in rules.AC_TYPES else ""
        lines.append(f"{'  ' * depth}{node['key']} [{node['type']}] {node['title']}{ac}")
        for c in node.get("children", []):
            walk(c, depth + 1)

    for node in plan["items"]:
        walk(node, 0)
    return "\n".join(lines)


def pr_title(s):
    return f"{s['title']} (#{s['number']})"


def render_pr_body(s, parent, commits, security):
    link = f"Closes #{s['number']}" + (f"\nParent: #{parent['number']} {parent['title']}" if parent else "")
    acs = parse_ac(parent["body"]) if parent and parent["type"] in rules.AC_TYPES else []
    parts = [("Liên kết", link), ("Thay đổi", "\n".join(f"- {c}" for c in commits) or "- (xem commit)")]
    if acs:
        parts.append(("Acceptance criteria liên quan", "\n".join(
            f"- AC{a['i']}: {a['text']}" + ("" if a["manual"] else f" → test `ac{parent['number']}_{a['i']}`")
            for a in acs)))
    parts += [("Kiểm thử", "- [x] lint/typecheck/scan/test pass (`check`)\n- [ ] CI xanh (`qa` kiểm)"),
              ("Security", "Có chạm security" if security else "Không chạm security")]
    return "\n\n".join(f"### {h}\n{v}" for h, v in parts)
```

- [ ] **Step 4: Chạy test** — Expected: PASS.
- [ ] **Step 5: Commit** — `git commit -am "feat(cli): helper pipeline (AC, nghiệm thu, security, context)"`

### Task 015: Lệnh pipeline context, start, check, submit, qa, accept, impact, plan-show

**Files:**
- Modify: `scripts/gh.py` (thêm cuối file), `scripts/omi.py` (thêm trước `def _num`)
- Test: `tests/test_cli_flow.py`

**Interfaces:**
- Consumes: Task 010 (`snapshot`, `cmd_move`, `cmd_rework`), Task 014.
- Produces:
  - gh: `issue_branches(cfg, n) -> list[str]`, `develop(cfg, n, cwd=None)`, `create_pr(cfg, title, body, head) -> int`, `pr_view(cfg, pr) -> tuple[str, str]`, `pr_diff(cfg, pr) -> str`, `pr_checks(cfg, pr) -> tuple[bool | None, str]` (None = PR không có CI), `merge_pr(cfg, pr)`.
  - omi: `run_cmd(cmd: str|list, cwd=None) -> tuple[int, str]` (lệnh git/test chạy với `cwd=repo_dir(cfg)`), `cmd_context(cfg, n) -> str`, `cmd_start(cfg, wf, n=None) -> int|None`, `cmd_check(cfg) -> int`, `cmd_submit(cfg, wf, n) -> tuple[int, list[str]]` (PR, reviewers), `cmd_qa(cfg, wf, n) -> int`, `cmd_accept(cfg, wf, n) -> int`, `cmd_impact(cfg, n, post=False) -> str`, `cmd_plan_show(wf, path) -> int`, `cmd_pr_lint(cfg, pr) -> int`. `start` ghi số task vào `.omi/tmp/current`, `qa` xóa khi Done (hook SessionStart dùng file này).
  - Dòng output (skill dựa vào): `START #n` | `NONE`; `CHECK PASS` | `CHECK FAIL (<bước>)`; `REVIEW #n PR #p pack=<file> reviewers=code[,security]|none`; `QA FAIL #n (<test|CI>) log=<file> status=<In Progress|Blocked>`; `DONE #n`; `ACCEPT PASS #p` | `ACCEPT FAIL #p: ...`; `PR OK` | `PR FAIL` + lỗi. `submit` chỉ đọc marker `<!-- omi:reviewed -->` (do `review-done` ở Task 020 ghi sau khi có kết quả review).

- [ ] **Step 1: Mở rộng `FakeGh` trong `tests/test_cli_flow.py`**

Thêm `import re` đầu file. Thêm vào `__init__`: `self.files, self.developed, self.branches = [], [], {}`; thêm `labels=()` vào `add()` (lưu `"labels": list(labels)`); thêm các method:

```python
    def merge_pr(self, cfg, pr):
        for i in self.issues.values():
            for p in i["prs"]:
                if p["number"] == pr:
                    p.update(state="MERGED", merged=True)

    def pr_checks(self, cfg, pr):
        return None, ""  # sandbox giả: không có CI → qa chạy commands.test

    def create_pr(self, cfg, title, body, head):
        n = int(re.search(r"Closes #(\d+)", body).group(1))
        self.issues[n]["prs"].append({"number": 50, "state": "OPEN", "merged": False})
        self.pr_created = (title, body)
        return 50

    def pr_files(self, cfg, pr):
        return self.files

    def pr_diff(self, cfg, pr):
        return "+x = 1"

    def issue_branches(self, cfg, n):
        return self.branches.get(n, [])

    def develop(self, cfg, n, cwd=None):
        self.developed.append(n)
```

`def add(self, n, type_, status, parent=None, state="OPEN", prs=(), body="", labels=()):` và trong dict thêm `"labels": list(labels)`.

- [ ] **Step 2: Thêm test**

```python
import tempfile
from unittest import mock

PCFG = {"commands": {"test": "T", "accept": "A {n}"}, "review_max_diff_lines": 100}
OPEN_PR = {"number": 50, "state": "OPEN", "merged": False}
AC1 = "### Acceptance criteria\n- [ ] đăng nhập được"


class TestPipeline(unittest.TestCase):
    def setUp(self):
        self.real_gh, self.real_tmp, self.g = omi.gh, omi.TMP, FakeGh()
        self.tmp = tempfile.TemporaryDirectory()
        omi.gh, omi.TMP = self.g, Path(self.tmp.name)

    def tearDown(self):
        omi.gh, omi.TMP = self.real_gh, self.real_tmp
        self.tmp.cleanup()

    def st(self, n):
        return self.g.issues[n]["status"]

    def test_start_moves_draft_to_in_progress_and_checks_out(self):
        self.g.add(2, "User Story", "Approved")
        self.g.add(3, "Task", "Draft", parent=2)
        self.assertEqual(omi.cmd_start(PCFG, WF, 3), 3)
        self.assertEqual(self.st(3), "In Progress")
        self.assertEqual(self.g.developed, [3])
        self.assertEqual((omi.TMP / "current").read_text(encoding="utf-8"), "3")

    def test_submit_first_time_requests_review_with_security(self):
        self.g.add(2, "User Story", "In Progress", body=AC1)
        self.g.add(3, "Task", "In Progress", parent=2)
        def fake_run(cmd, cwd=None):
            cmd = " ".join(cmd) if isinstance(cmd, list) else cmd
            if cmd.startswith("git diff"):
                return 0, "src/auth/login.py\n"
            if cmd.startswith("git log"):
                return 0, "#3: thêm login\n"
            return 0, "omi/3-login"

        with mock.patch.object(omi, "run_cmd", side_effect=fake_run):
            pr, reviewers = omi.cmd_submit(PCFG, WF, 3)
        self.assertEqual((pr, reviewers, self.st(3)), (50, ["code", "security"], "In Review"))
        title, body = self.g.pr_created
        self.assertEqual(title, "#3 (#3)")
        self.assertIn("Closes #3", body)
        self.assertIn("- #3: thêm login", body)
        self.assertIn("Có chạm security", body)
        self.assertIn("+x = 1", (omi.TMP / "review-3.md").read_text(encoding="utf-8"))
        self.assertFalse(any("omi:reviewed" in c for c in self.g.notes.get(3, [])))  # marker do review-done ghi

    def test_submit_after_rework_skips_review(self):
        self.g.add(2, "User Story", "In Progress")
        self.g.add(3, "Task", "In Progress", parent=2, prs=[dict(OPEN_PR)])
        self.g.notes[3] = ["<!-- omi:reviewed -->"]
        with mock.patch.object(omi, "run_cmd", return_value=(0, "")):
            self.assertEqual(omi.cmd_submit(PCFG, WF, 3), (50, []))
        self.assertEqual(self.st(3), "In Review")

    def test_qa_pass_merges_done_and_accepts_parent(self):
        self.g.add(1, "Epic", "In Progress")
        self.g.add(2, "User Story", "In Progress", parent=1, body=AC1)
        self.g.add(3, "Task", "In Review", parent=2, prs=[dict(OPEN_PR)])
        with mock.patch.object(omi, "run_cmd", return_value=(0, "test_ac2_1 ... ok")):
            self.assertEqual(omi.cmd_qa(PCFG, WF, 3), 0)
        self.assertEqual((self.st(3), self.st(2), self.st(1)), ("Done", "Done", "Done"))
        self.assertFalse((omi.TMP / "current").exists())

    def test_qa_fail_reworks_and_writes_log(self):
        self.g.add(2, "User Story", "In Progress")
        self.g.add(3, "Task", "In Review", parent=2, prs=[dict(OPEN_PR)])
        with mock.patch.object(omi, "run_cmd", return_value=(1, "AssertionError: boom")):
            self.assertEqual(omi.cmd_qa(PCFG, WF, 3), 1)
        self.assertEqual((self.st(3), self.g.issues[3]["rework_count"]), ("In Progress", 1))
        self.assertIn("boom", (omi.TMP / "qa-3.log").read_text(encoding="utf-8"))

    def test_accept_manual_unticked_stays_in_qa(self):
        self.g.add(2, "User Story", "In QA", body="### Acceptance criteria\n- [ ] [manual] UI")
        self.assertEqual(omi.cmd_accept(PCFG, WF, 2), 1)
        self.assertEqual((self.st(2), self.g.issues[2]["rework_count"]), ("In QA", 0))

    def test_accept_auto_fail_reworks(self):
        self.g.add(2, "User Story", "In QA", body=AC1)
        with mock.patch.object(omi, "run_cmd", return_value=(0, "nothing")):
            self.assertEqual(omi.cmd_accept(PCFG, WF, 2), 1)
        self.assertEqual(self.st(2), "In Progress")
```

- [ ] **Step 3: Chạy để thấy thất bại** — Expected: `AttributeError ... 'cmd_start'`.

- [ ] **Step 4: Thêm vào `scripts/gh.py`**

```python
# ---------- branch / PR ----------
def issue_branches(cfg, n):
    out = run(["issue", "develop", "--list", str(n), "-R", _repo(cfg)])
    return [line.split()[0] for line in out.splitlines() if line.strip()]


def develop(cfg, n, cwd=None):
    run(["issue", "develop", str(n), "-R", _repo(cfg), "--checkout"], cwd=cwd)


def create_pr(cfg, title, body, head):
    url = run(["pr", "create", "-R", _repo(cfg), "--head", head, "--title", title,
               "--body-file", "-"], input=body).strip().splitlines()[-1]
    return int(url.rstrip("/").split("/")[-1])


def pr_view(cfg, pr):
    d = json.loads(run(["pr", "view", str(pr), "-R", _repo(cfg), "--json", "title,body"]))
    return d["title"], d["body"]


def pr_diff(cfg, pr):
    return run(["pr", "diff", str(pr), "-R", _repo(cfg)])


def pr_checks(cfg, pr):
    """(True|False, output) khi PR có CI; (None, "") khi không có check nào."""
    try:
        return True, run(["pr", "checks", str(pr), "-R", _repo(cfg), "--watch", "--fail-fast"])
    except GhError as e:
        if "no checks reported" in str(e).lower():
            return None, ""
        return False, str(e)


def merge_pr(cfg, pr):
    run(["pr", "merge", str(pr), "-R", _repo(cfg), "--squash", "--delete-branch"])
```

- [ ] **Step 5: Thêm vào `scripts/omi.py` (trước `def _num`)**

```python
CHECK_STEPS = ("lint", "typecheck", "scan", "test")


def run_cmd(cmd, cwd=None):
    """str = lệnh của dự án (qua shell); list = lệnh nội bộ như git (không qua shell, tránh injection)."""
    p = subprocess.run(cmd, shell=isinstance(cmd, str), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", cwd=cwd)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def _open_pr(snap):
    return next((p["number"] for p in snap["prs"] if p["state"] == "OPEN"), None)


def cmd_context(cfg, n):
    s = gh.issue_snapshot(cfg, n)
    parent = gh.issue_snapshot(cfg, s["parent"]["number"]) if s["parent"] else None
    text = render_context(s, parent, [gh.issue_snapshot(cfg, a) for a in affected(s["body"])])
    print(text)
    return text


def cmd_start(cfg, wf, n=None):
    if n is None:
        it = rules.pick_next(wf, gh.project_items(cfg))
        if not it:
            print("NONE")
            return None
        n = it["number"]
    status = snapshot(cfg, n)["status"]
    if status == "Draft":
        cmd_move(cfg, wf, n, "Ready")
        status = "Ready"
    if status == "Ready":
        cmd_move(cfg, wf, n, "In Progress")
    elif status != "In Progress":
        raise RuleError(f"#{n} đang ở '{status}', không start được")
    branches = gh.issue_branches(cfg, n)
    if branches:
        run_cmd(["git", "fetch", "origin"], cwd=repo_dir(cfg))
        code, out = run_cmd(["git", "checkout", branches[0]], cwd=repo_dir(cfg))
        if code:
            raise RuleError("git checkout lỗi:\n" + tail(out, 10))
    else:
        gh.develop(cfg, n, cwd=repo_dir(cfg))
    TMP.mkdir(parents=True, exist_ok=True)
    (TMP / "current").write_text(str(n), encoding="utf-8")  # hook SessionStart nạp lại context sau /clear
    print(f"START #{n}")
    return n


def cmd_check(cfg):
    for step in CHECK_STEPS:
        cmd = cfg.get("commands", {}).get(step)
        if cmd:
            code, out = run_cmd(cmd, cwd=repo_dir(cfg))
            if code:
                print(f"CHECK FAIL ({step})\n{tail(out)}")
                return 1
    print("CHECK PASS")
    return 0


def cmd_submit(cfg, wf, n):
    s = snapshot(cfg, n)
    if s["status"] not in ("In Progress", "In Review"):
        raise RuleError(f"#{n} phải ở In Progress/In Review (hiện: {s['status']})")
    code, out = run_cmd(["git", "push", "-u", "origin", "HEAD"], cwd=repo_dir(cfg))
    if code:
        raise RuleError("git push lỗi:\n" + tail(out, 20))
    parent = gh.issue_snapshot(cfg, s["parent"]["number"]) if s["parent"] else None
    base = f"origin/{cfg.get('default_branch', 'main')}"
    _, files = run_cmd(["git", "diff", "--name-only", f"{base}...HEAD"], cwd=repo_dir(cfg))
    sec = needs_security(files.split(), s["labels"] + (parent["labels"] if parent else []), parent,
                         cfg.get("security_paths", DEFAULT_SECURITY))
    pr = _open_pr(s)
    if pr is None:  # title + body PR theo pr_template.json, do script sinh
        _, log = run_cmd(["git", "log", "--format=%s", f"{base}..HEAD"], cwd=repo_dir(cfg))
        _, head = run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_dir(cfg))
        pr = gh.create_pr(cfg, pr_title(s), render_pr_body(s, parent, log.splitlines(), sec), head.strip())
    if s["status"] == "In Progress":
        cmd_move(cfg, wf, n, "In Review")
    reviewers = []
    if find_marker(gh.comments(cfg, n), "reviewed") is None:  # review LLM chỉ 1 lượt mỗi task
        reviewers = ["code"] + (["security"] if sec else [])
        diff = gh.pr_diff(cfg, pr).splitlines()
        limit = cfg.get("review_max_diff_lines", 1500)
        TMP.mkdir(parents=True, exist_ok=True)
        pack = TMP / f"review-{n}.md"
        pack.write_text(
            render_context(s, parent, [gh.issue_snapshot(cfg, a) for a in affected(s["body"])])
            + f"\n\n## Diff PR #{pr} ({len(diff)} dòng)\n```diff\n" + "\n".join(diff[:limit])
            + ("\n... (đã cắt)" if len(diff) > limit else "") + "\n```\n", encoding="utf-8")
        print(f"REVIEW #{n} PR #{pr} pack={pack.as_posix()} reviewers={','.join(reviewers)}")
    else:
        print(f"REVIEW #{n} PR #{pr} reviewers=none")
    return pr, reviewers


def cmd_qa(cfg, wf, n):
    s = snapshot(cfg, n)
    if s["status"] == "In Review":
        cmd_move(cfg, wf, n, "In QA")
    elif s["status"] != "In QA":
        raise RuleError(f"#{n} phải ở In Review/In QA (hiện: {s['status']})")
    pr = _open_pr(s)
    if pr is None:
        raise RuleError(f"#{n} không có PR mở")
    ok, out = gh.pr_checks(cfg, pr)
    why = "CI"
    if ok is None:  # không có CI: chạy test cục bộ; có CI thì không chạy trùng
        test = cfg.get("commands", {}).get("test")
        if not test:
            raise RuleError("PR không có CI và chưa cấu hình commands.test trong .omi/project.json")
        code, out = run_cmd(test, cwd=repo_dir(cfg))
        ok, why = code == 0, "test"
    if not ok:
        TMP.mkdir(parents=True, exist_ok=True)
        log = TMP / f"qa-{n}.log"
        log.write_text(tail(out, 200), encoding="utf-8")
        status = cmd_rework(cfg, wf, n, f"QA fail ({why}), log: {log.as_posix()}")
        print(f"QA FAIL #{n} ({why}) log={log.as_posix()} status={status}")
        return 1
    gh.merge_pr(cfg, pr)
    cmd_move(cfg, wf, n, "Done")
    print(f"DONE #{n}")
    (TMP / "current").unlink(missing_ok=True)
    if s["parent"]:
        p = snapshot(cfg, s["parent"]["number"])
        if p["status"] == "In QA" and p["type"] in rules.AC_TYPES:
            cmd_accept(cfg, wf, p["number"])
    return 0


def cmd_accept(cfg, wf, n):
    s = snapshot(cfg, n)
    if s["status"] != "In QA":
        raise RuleError(f"#{n} phải ở In QA (hiện: {s['status']})")
    acs = parse_ac(s["body"])
    if not acs:
        raise RuleError(f"#{n} không có mục '### Acceptance criteria'")
    code, out = 0, ""
    if any(not a["manual"] for a in acs):
        cmd = cfg.get("commands", {}).get("accept")
        if not cmd:
            raise RuleError("Chưa cấu hình commands.accept trong .omi/project.json")
        code, out = run_cmd(cmd.format(n=n), cwd=repo_dir(cfg))
    ok, missing = accept_verdict(n, acs, out, code)
    if ok:
        cmd_move(cfg, wf, n, "Done")
        print(f"ACCEPT PASS #{n}")
        return 0
    print(f"ACCEPT FAIL #{n}: " + "; ".join(missing))
    if any("[manual]" not in m for m in missing):
        cmd_rework(cfg, wf, n, "Nghiệm thu fail: " + "; ".join(missing))
    return 1


def cmd_impact(cfg, n, post=False):
    s = snapshot(cfg, n)
    lines = ["<!-- omi:impact -->", f"## Ảnh hưởng của Change Request #{n}"]
    for a in affected(s["body"]):
        x = gh.issue_snapshot(cfg, a)
        lines.append(f"- #{a} {x['title']} — {x['status']}")
        lines += [f"  - #{c['number']} {c['title']} — {c['status']}" for c in x["children"]]
    text = "\n".join(lines)
    print(text)
    if post:
        gh.comment(cfg, n, text)
    return text


def cmd_plan_show(wf, path):
    plan = json.loads(Path(path).read_text(encoding="utf-8"))
    errs = rules.validate_plan(wf, plan, rules.load_templates())
    if errs:
        raise RuleError(errs)
    print(render_plan(plan))
    return 0


def cmd_pr_lint(cfg, pr):
    title, body = gh.pr_view(cfg, pr)
    errs = rules.check_pr(rules.load_pr_template(), title, body)
    print("PR OK" if not errs else "PR FAIL\n" + "\n".join(f"- {e}" for e in errs))
    return 1 if errs else 0
```

- [ ] **Step 6: Chạy test** — Run: `python -m unittest discover -s tests -v` — Expected: PASS.

- [ ] **Step 7: Commit** — `git add -A && git commit -m "feat(cli): pipeline context/start/check/submit/qa/accept/impact/plan-show"`

---

## Phase 4 — Plugin Claude Code

### Task 016: Hooks gác cổng

**Files:**
- Create: `hooks/guard.py`, `hooks/hooks.json`, `tests/test_guard.py`

**Interfaces:**
- Produces: `guard.decide(command: str) -> tuple[str, str] | None` (`("deny"|"ask", lý do)`), `guard.session_text(plugin_root: Path, cwd: Path, source: str = "startup", run=_run) -> str` (sau `startup`/`clear`: in context task trong `.omi/tmp/current` hoặc `NEXT`).

- [ ] **Step 1: Viết test thất bại `tests/test_guard.py`**

```python
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hooks"))
import guard  # noqa: E402


class TestDecide(unittest.TestCase):
    def test_deny_shortcuts(self):
        for c in ["gh issue close 12", "gh issue reopen 3 -R a/b", "gh project item-edit --id X",
                  "gh api graphql -f query='mutation{updateProjectV2ItemFieldValue(...)}'"]:
            self.assertEqual(guard.decide(c)[0], "deny", c)

    def test_ask_on_approve(self):
        self.assertEqual(guard.decide('python "C:/p/scripts/omi.py" move 12 Approved')[0], "ask")
        self.assertEqual(guard.decide('python /p/scripts/omi.py move #12 "Approved"')[0], "ask")
        self.assertEqual(guard.decide("python omi.py apply .omi/plans/a.json --approve")[0], "ask")

    def test_allow_normal(self):
        for c in ["python omi.py move 12 Done", "gh issue view 3", "gh pr create --fill", "git status"]:
            self.assertIsNone(guard.decide(c), c)


class TestSession(unittest.TestCase):
    def test_prints_one_line_cli_and_hint(self):
        t = guard.session_text(Path("/plug"), Path("/nonexistent-repo"))
        self.assertTrue(t.startswith("OMI_CLI: python"))
        self.assertIn("scripts", t)
        self.assertIn("init", t)
        self.assertEqual(len(t.splitlines()), 1)

    def test_reloads_task_context_after_clear(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d) / ".omi" / "tmp"
            tmp.mkdir(parents=True)
            (Path(d) / ".omi" / "project.json").write_text("{}", encoding="utf-8")
            (tmp / "current").write_text("7", encoding="utf-8")
            calls = []

            def fake(args, cwd):
                calls.append(args[-2:])
                return "# #7 [Task] Làm form đăng nhập"

            t = guard.session_text(Path("/plug"), Path(d), "clear", fake)
            self.assertIn("omi-resume", t)
            self.assertIn("# #7 [Task]", t)
            self.assertEqual(calls[0][-1], "resume")
            (tmp / "current").unlink()
            self.assertIn("NEXT: #8", guard.session_text(Path("/plug"), Path(d), "clear", lambda a, c: "#8 [Task] Y"))
            self.assertEqual(len(guard.session_text(Path("/plug"), Path(d), "resume", fake).splitlines()), 1)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Chạy để thấy thất bại** — Expected: `ModuleNotFoundError: No module named 'guard'`.

- [ ] **Step 3: Viết `hooks/guard.py`**

```python
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
]


def decide(command):
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
```

- [ ] **Step 4: Viết `hooks/hooks.json`**

```json
{
  "hooks": {
    "PreToolUse": [
      {"matcher": "Bash|PowerShell",
       "hooks": [{"type": "command", "command": "python \"${CLAUDE_PLUGIN_ROOT}/hooks/guard.py\" pre"}]}
    ],
    "SessionStart": [
      {"hooks": [{"type": "command", "command": "python \"${CLAUDE_PLUGIN_ROOT}/hooks/guard.py\" session"}]}
    ]
  }
}
```

- [ ] **Step 5: Chạy test** — Expected: PASS.

- [ ] **Step 6: Kiểm tra hook bằng stdin thật**

```bash
echo '{"tool_input":{"command":"gh issue close 5"}}' | python hooks/guard.py pre
```
Expected: JSON có `"permissionDecision": "deny"`.

- [ ] **Step 7: Commit** — `git add hooks tests/test_guard.py && git commit -m "feat(hooks): gác cổng PreToolUse + SessionStart OMI_CLI"`

### Task 017: Manifest và skill `omi-change` (Change Request + Bug)

Không có skill cho init/move/tree/next: người dùng chạy thẳng `OMI_CLI ...` trong terminal hoặc gõ `!` trong Claude Code (0 token LLM).

**Files:**
- Create: `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `skills/omi-change/SKILL.md`

**Interfaces:**
- Consumes: lệnh CLI `new`, `impact`, `move` (Task 010, 11B); dòng `OMI_CLI:` (Task 016).

- [ ] **Step 1: `.claude-plugin/plugin.json`**

```json
{
  "name": "omi-hub",
  "version": "0.1.0",
  "description": "Quy trình dự án chuẩn trên GitHub Projects cho Claude Code, tối ưu token: script làm mọi việc tất định.",
  "author": {"name": "omi-home"}
}
```

- [ ] **Step 2: `.claude-plugin/marketplace.json`**

```json
{
  "name": "omi-home",
  "owner": {"name": "omi-home"},
  "plugins": [
    {"name": "omi-hub", "source": "./", "description": "Quy trình dự án chuẩn trên GitHub Projects cho Claude Code."}
  ]
}
```

- [ ] **Step 3: `skills/omi-change/SKILL.md`**

```markdown
---
name: omi-change
description: Tạo và xử lý Change Request (đổi yêu cầu đã Approved) hoặc Bug (lỗi trên item đã Done) trong repo omi.
---

`OMI_CLI` = lệnh ở dòng `OMI_CLI:` đầu phiên. Không đọc code trừ khi người dùng yêu cầu.

## Change Request
1. `OMI_CLI new "Change Request" "Thay đổi <đối tượng>: <tóm tắt>" --parent <epic> --affects <a,b> --field "Lý do thay đổi=..." --field "Nội dung thay đổi=<trước → sau>"` (khung đầy đủ: `OMI_CLI template "Change Request"`).
2. `OMI_CLI impact <cr> --post` (script liệt kê item bị ảnh hưởng và item con).
3. Chỉ dựa trên danh sách đó, đề xuất cho người dùng: Task cần thêm (tiêu đề một dòng, parent), Task cần hủy.
4. Người dùng đồng ý → `OMI_CLI move <cr> Approved`; `OMI_CLI new Task "<động từ> <đối tượng>" --parent <cr> --field "Việc cần làm=..."` rồi `move <task> Ready`; hủy: `OMI_CLI move <task> Cancelled --reason "Thay bởi Change Request #<cr>"`. Từ chối → `OMI_CLI move <cr> Cancelled --reason "<lý do>"`.
5. Làm các Task bằng skill omi-implement. Change Request tự Done khi Task xong.

## Bug
1. `OMI_CLI new Bug "<thành phần>: <triệu chứng>" --affects <n> --milestone <m> --field "Các bước tái hiện=..." --field "Kết quả mong đợi=..." --field "Kết quả thực tế=..."` (khung: `OMI_CLI template Bug`).
2. Bước tái hiện rõ ràng → `OMI_CLI move <bug> Ready`. Không phải lỗi/trùng → `OMI_CLI move <bug> Cancelled --reason "..."`.
3. Sửa bằng skill omi-implement (bước đầu: viết test tái hiện fail).
```

- [ ] **Step 4: Kiểm tra JSON**

Run: `python -c "import json;[json.load(open(p,encoding='utf-8')) for p in ['.claude-plugin/plugin.json','.claude-plugin/marketplace.json','hooks/hooks.json']]"`
Expected: không lỗi. (Nếu Claude Code có `claude plugin validate .` thì chạy thêm.)

- [ ] **Step 5: Commit** — `git add .claude-plugin skills/omi-change && git commit -m "feat(plugin): manifest và skill omi-change"`

### Task 018: Subagent review và skill `omi-implement`

**Files:**
- Create: `agents/omi-reviewer.md`, `agents/omi-security-reviewer.md`, `skills/omi-implement/SKILL.md`

**Interfaces:**
- Consumes: output `START`, `CHECK`, `REVIEW`, `QA FAIL`, `DONE`, `ACCEPT` (Task 015).
- Produces: subagent trả dòng đầu `VERDICT: PASS|FAIL`, các dòng `BLOCKER: ...`, `IMPROVE: ...`.

- [ ] **Step 1: `agents/omi-reviewer.md`**

````markdown
---
name: omi-reviewer
description: Code review 1 lượt cho gói review omi (AC + diff). Chỉ báo blocker theo checklist.
tools: Read, Grep, Glob
model: sonnet
memory: project
---

Input: đường dẫn gói review (`Pack: <file>`).

1. Đọc memory của bạn (≤ 30 dòng) rồi đọc gói. Chỉ mở file khác khi cần xác minh một dòng cụ thể trong diff.
2. Checklist blocker: sai so với yêu cầu/AC; lỗi logic hoặc edge case làm sai kết quả; thiếu test cho hành vi chính; thay đổi ngoài phạm vi task.
3. Bỏ qua: phong cách, đặt tên, format, những gì lint/typecheck/test đã kiểm. Đây là lượt review duy nhất: chỉ báo vấn đề chắc chắn, không suy đoán.
4. Cải tiến không bắt buộc → `IMPROVE:` (không ảnh hưởng verdict).

Output (tối đa 12 dòng, không khen, không giải thích dài):
```
VERDICT: PASS|FAIL
BLOCKER: <file>:<line> <vấn đề> → <cách sửa ngắn>
IMPROVE: <gợi ý một dòng>
```

Chỉ cập nhật memory khi phát hiện quy ước hoặc lỗi lặp lại mới của dự án; giữ memory ≤ 30 dòng.
````

- [ ] **Step 2: `agents/omi-security-reviewer.md`**

````markdown
---
name: omi-security-reviewer
description: Security review 1 lượt cho gói review omi khi script phát hiện task chạm security.
tools: Read, Grep, Glob
model: sonnet
memory: project
---

Input: đường dẫn gói review (`Pack: <file>`).

1. Đọc memory (≤ 30 dòng) rồi đọc gói. Chỉ mở file khác khi cần lần theo luồng dữ liệu của một dòng trong diff.
2. Checklist: injection (SQL/command/path/template); authn/authz thiếu hoặc sai; secret/credential trong code hoặc log; crypto sai (thuật toán yếu, IV/salt cố định, so sánh không constant-time); thiếu validate input ở biên tin cậy; lộ dữ liệu nhạy cảm qua response/log.
3. Mỗi blocker phải có dòng cụ thể và kịch bản khai thác thực tế. Không báo rủi ro chung chung, không báo thứ tool scan đã bắt. Đây là lượt duy nhất.

Output (tối đa 12 dòng):
```
VERDICT: PASS|FAIL
BLOCKER: <file>:<line> <lỗ hổng> | khai thác: <một câu> → <cách sửa>
IMPROVE: <hardening không bắt buộc>
```

Chỉ cập nhật memory với pattern bảo mật lặp lại của dự án; giữ ≤ 30 dòng.
````

- [ ] **Step 3: `skills/omi-implement/SKILL.md`**

```markdown
---
name: omi-implement
description: Làm một Task/Bug omi tới Done (start → code → check → submit → review 1 lượt → qa).
---

`OMI_CLI` = lệnh ở dòng `OMI_CLI:` đầu phiên. Bạn tự viết và tự sửa code trong phiên này; không giao code cho subagent.

1. Đầu phiên đã có dòng `RESUME` → làm theo skill omi-resume. Nếu không: `OMI_CLI start [n]` → `START #n` (hoặc `NONE`: báo và dừng), rồi `OMI_CLI context n`.
2. TDD: test trước (Bug: test tái hiện; AC của parent #p: test tên chứa `ac<p>_<i>`), rồi code. Chỉ đọc file cần thiết. Lặp `OMI_CLI check` tới `CHECK PASS`. Commit `#n: <tóm tắt>`.
3. `OMI_CLI submit n` → `REVIEW #n PR #pr pack=<f> reviewers=<...>`.
4. Nếu `reviewers` khác `none`: gọi song song subagent `omi-hub:omi-reviewer` và (nếu có `security`) `omi-hub:omi-security-reviewer`, prompt đúng một dòng `Pack: <f>`.
   - Mỗi `IMPROVE:` → `OMI_CLI new Task "<gợi ý ngắn>" --parent <parent của n> --field "Việc cần làm=<gợi ý>"` (Draft). Không làm trong task này.
   - Không có `BLOCKER:` → `OMI_CLI review-done n`.
   - Có `BLOCKER:` → `OMI_CLI review-done n --fail "<blocker gộp ≤ 3 dòng>"` (script ghi nhận + rework) → sửa → `check` → `submit n` (lần này `reviewers=none`, không review lại).
5. `OMI_CLI qa n`:
   - `QA FAIL ... log=<f> status=In Progress` → đọc log, sửa, `check`, `submit n`, `qa n`.
   - `status=Blocked` → dừng, báo người dùng (vượt 3 lần rework).
   - `DONE #n`. Nếu có `ACCEPT FAIL #p` với AC tự động → `OMI_CLI new Task "Đạt AC<i> của #p" --parent p --field "Việc cần làm=<nội dung AC>"`, `move` Ready, báo người dùng. AC `[manual]` → nhắc người dùng tick.
6. Báo một dòng: `#n Done · PR #pr · rework k · task mới: ...` và nhắc: "Gõ `/clear` rồi `tiếp` — hook tự nạp task kế tiếp".
```

- [ ] **Step 4: Thử trên sandbox**: `claude --plugin-dir <omi-hub>` trong clone sandbox → kiểm tra dòng `OMI_CLI:` đầu phiên; gọi skill omi-implement với một Task Ready; xác nhận review chỉ chạy một lần (lần `submit` thứ hai in `reviewers=none`); yêu cầu "chạy gh issue close 1" → hook chặn.

- [ ] **Step 5: Commit** — `git add agents skills/omi-implement && git commit -m "feat(plugin): reviewer 1 lượt và skill omi-implement"`

### Task 019: Skill `omi-plan`

**Files:**
- Create: `skills/omi-plan/SKILL.md`

**Interfaces:**
- Consumes: định dạng plan (Task 012), `plan-show` (Task 015), `apply`.

- [ ] **Step 1: `skills/omi-plan/SKILL.md`**

````markdown
---
name: omi-plan
description: Phân rã PRD thành plan JSON omi (Epic → Story/Functional Requirement/Non-Functional Requirement → Task); script kiểm tra, vẽ cây và tạo issue.
---

`OMI_CLI` = lệnh ở dòng `OMI_CLI:` đầu phiên.

1. Đọc tài liệu người dùng chỉ định. Điểm mơ hồ ảnh hưởng cấu trúc → hỏi từng câu một.
2. Ghi `.omi/plans/<YYYY-MM-DD>-<slug>.json`. Không tự vẽ cây trong câu trả lời.
   - Epic: capability lớn. Story: giá trị cho một vai trò. Functional Requirement: hành vi hệ thống. Non-Functional Requirement: chất lượng đo được (có ngưỡng). Task: ≤ 1 ngày, luôn dưới Story/Functional Requirement/Non-Functional Requirement. Không có Change Request.
   - Story/Functional Requirement/Non-Functional Requirement có `### Acceptance criteria` dạng `- [ ]`, mỗi dòng kiểm chứng được bằng test; không tự động hóa được thì ghi `[manual]`.
   - Title và body mỗi node theo template của loại (`OMI_CLI template <type>`, mục `### ...` đúng tên).
   - Key phân cấp ổn định (`E001.S002.T003`). Gắn vào issue có sẵn: `"parent": <số>` ở node gốc.

```json
{"milestone": "v1.0", "items": [
  {"key": "E001", "type": "Epic", "title": "Quản lý đơn hàng", "priority": "P1",
   "body": "### Mục tiêu\n...\n\n### Phạm vi\n- ...", "children": [
    {"key": "E001.S001", "type": "User Story", "title": "Khách hàng có thể đặt hàng", "estimate": 3,
     "body": "### Story\nLà khách, tôi muốn ... để ...\n\n### Acceptance criteria\n- [ ] ...", "children": [
      {"key": "E001.S001.T001", "type": "Task", "title": "Thêm API POST /orders",
       "body": "### Việc cần làm\n...\n\n### Definition of done\n- [ ] Test pass"}]}]}]}
```
3. `OMI_CLI plan-show <file>`: lỗi → sửa file, chạy lại. Hợp lệ → báo người dùng đường dẫn file và bảo họ xem output cây (không chép lại cây).
4. Người dùng đồng ý (= chốt baseline) → `OMI_CLI apply <file> --approve`; chỉ muốn nháp → `OMI_CLI apply <file>`. Chạy lại apply an toàn (bỏ qua key đã có).
````

- [ ] **Step 2: Thử trên sandbox**: PRD ngắn 2 story → `plan-show` hợp lệ → `apply --approve` → `OMI_CLI tree` đúng cây.

- [ ] **Step 3: Commit** — `git add skills/omi-plan && git commit -m "feat(plugin): skill omi-plan"`

---

## Phase 5 — Kiểm thử đầu-cuối và phát hành

### Task 020: Lệnh status, resume, review-done và skill omi-status, omi-resume

Script-first: toàn bộ logic nằm trong CLI; hai skill chỉ là lớp mỏng gọi CLI. Gõ `! <OMI_CLI> status` là 0 token.

**Files:**
- Modify: `scripts/omi.py` (thêm trước `def _num`), `scripts/gh.py` (Task 007 đã có `rework` trong `ITEMS_QUERY`)
- Create: `skills/omi-status/SKILL.md`, `skills/omi-resume/SKILL.md`
- Test: `tests/test_cli.py`, `tests/test_cli_flow.py`

**Interfaces:**
- Consumes: `gh.project_items` (có `rework_count`), `rules.pick_next`, `cmd_context`, `cmd_rework`, `find_marker`, `repo_dir`, `run_cmd`, `TMP`.
- Produces: `omi.render_status(wf, items, milestone=None) -> str`, `omi.resume_step(status, dirty: bool, ahead: int, reviewed: bool, pack_exists: bool) -> tuple[str, str]`, `omi.cmd_status(cfg, wf, milestone=None) -> str`, `omi.cmd_resume(cfg, wf) -> str|None` (bước), `omi.cmd_review_done(cfg, wf, n, fail=None)`.
- Output: `STATUS ...`; `RESUME #n status=<S> step=<code|submit|review|qa|blocked|start|next>` + gợi ý (+ context khi step là `code`/`submit`); `RESUME none step=next`; `REVIEWED #n PASS|FAIL`.

- [ ] **Step 1: Thêm test vào `tests/test_cli.py`**

```python
def pitem(n, type_, status, parent=None, **kw):
    base = {"number": n, "title": f"[{type_}] item {n}", "type": type_, "status": status, "state": "OPEN",
            "parent": parent, "milestone": "v1", "milestone_due": None, "priority": "P1",
            "open_blockers": 0, "blocked_reason": None, "rework_count": 0}
    base.update(kw)
    return base


class TestStatusResume(unittest.TestCase):
    def test_render_status(self):
        items = [pitem(1, "Epic", "In Progress"), pitem(2, "User Story", "In Progress", 1),
                 pitem(3, "Task", "Done", 2), pitem(4, "Task", "In Review", 2, rework_count=2),
                 pitem(5, "Task", "Blocked", 2, blocked_reason="chờ API key"), pitem(6, "Task", "Ready", 2),
                 pitem(7, "Task", "Cancelled", 2)]
        out = omi.render_status(omi.rules.load_workflow(), items)
        self.assertIn("STATUS: 1/6 (16%) item Done · Task/Bug 1/4 (25%)", out)
        self.assertIn("- #1 [Epic] item 1 — In Progress · 1/5 (20%)", out)
        self.assertIn("- #4 [Task] item 4 — In Review", out)
        self.assertIn("chờ API key", out)
        self.assertIn("2 lần", out)
        self.assertIn("Tiếp theo: #6", out)
        self.assertIn("STATUS v2: 0/0", omi.render_status(omi.rules.load_workflow(), items, "v2"))

    def test_resume_step(self):
        rs = omi.resume_step
        self.assertEqual(rs("In Progress", True, 0, False, False)[0], "code")
        self.assertEqual(rs("In Progress", False, 0, False, False)[0], "code")
        self.assertEqual(rs("In Progress", False, 2, False, False)[0], "submit")
        self.assertEqual(rs("In Review", False, 2, False, True)[0], "review")
        self.assertIn("submit", rs("In Review", False, 2, False, False)[1])  # mất gói review → submit lại
        self.assertEqual(rs("In Review", False, 2, True, True)[0], "qa")
        self.assertEqual(rs("In QA", False, 0, True, False)[0], "qa")
        self.assertEqual(rs("Blocked", False, 0, False, False)[0], "blocked")
        self.assertEqual(rs("Ready", False, 0, False, False)[0], "start")
        self.assertEqual(rs("Done", False, 0, True, False)[0], "next")
```

- [ ] **Step 2: Thêm test vào `tests/test_cli_flow.py` (class `TestPipeline`)**

```python
    def test_review_done_fail_marks_and_reworks(self):
        self.g.add(2, "User Story", "In Progress")
        self.g.add(3, "Task", "In Review", parent=2, prs=[dict(OPEN_PR)])
        omi.cmd_review_done(PCFG, WF, 3, "thiếu test cho case rỗng")
        self.assertEqual((self.st(3), self.g.issues[3]["rework_count"]), ("In Progress", 1))
        self.assertTrue(any("omi:reviewed" in c for c in self.g.notes[3]))

    def test_resume_after_crash_before_review(self):
        self.g.add(2, "User Story", "In Progress")
        self.g.add(3, "Task", "In Review", parent=2, prs=[dict(OPEN_PR)])
        (omi.TMP / "current").write_text("3", encoding="utf-8")
        (omi.TMP / "review-3.md").write_text("pack", encoding="utf-8")
        with mock.patch.object(omi, "run_cmd", return_value=(0, "")):
            self.assertEqual(omi.cmd_resume(PCFG, WF), "review")

    def test_resume_done_task_clears_current(self):
        self.g.add(3, "Task", "Done", state="CLOSED")
        (omi.TMP / "current").write_text("3", encoding="utf-8")
        with mock.patch.object(omi, "run_cmd", return_value=(0, "")):
            self.assertEqual(omi.cmd_resume(PCFG, WF), "next")
        self.assertFalse((omi.TMP / "current").exists())
```

- [ ] **Step 3: Chạy để thấy thất bại** — Expected: `AttributeError ... 'render_status'`.

- [ ] **Step 4: Thêm vào `scripts/omi.py` (trước `def _num`)**

```python
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
    section("Rework:", [f"- #{i['number']} {i['title']} — {i['rework_count']} lần" for i in live if i.get("rework_count")])
    nxt = rules.pick_next(wf, items)
    lines.append(f"Tiếp theo: #{nxt['number']} {nxt['title']}" if nxt else "Tiếp theo: (không có Task/Bug Ready)")
    return "\n".join(lines)


def cmd_status(cfg, wf, milestone=None):
    text = render_status(wf, [i for i in gh.project_items(cfg) if i["title"] != gh.AUDIT_TITLE], milestone)
    print(text)
    return text


def resume_step(status, dirty, ahead, reviewed, pack_exists):
    """Bước tiếp theo của task dở, suy ra thuần từ trạng thái (GitHub + git + .omi/tmp)."""
    if status in (None, "Done", "Cancelled"):
        return "next", "Task đã kết thúc → `start` lấy task tiếp."
    if status == "Blocked":
        return "blocked", "Task đang Blocked → báo người dùng lý do, chờ `unblock`."
    if status in ("Draft", "Triage", "Ready"):
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


def cmd_resume(cfg, wf):
    cur = TMP / "current"
    if not cur.exists():
        print("RESUME none step=next — không có task dở; `start` để lấy task tiếp.")
        return None
    n = int(cur.read_text(encoding="utf-8").strip())
    s = gh.issue_snapshot(cfg, n)
    rd, base = repo_dir(cfg), f"origin/{cfg.get('default_branch', 'main')}"
    _, dirty = run_cmd(["git", "status", "--porcelain"], cwd=rd)
    _, ahead = run_cmd(["git", "rev-list", "--count", f"{base}..HEAD"], cwd=rd)
    reviewed = find_marker(gh.comments(cfg, n), "reviewed") is not None
    step, hint = resume_step(s["status"], bool(dirty.strip()), int(ahead.strip()) if ahead.strip().isdigit() else 0,
                             reviewed, (TMP / f"review-{n}.md").exists())
    if step == "next":
        cur.unlink(missing_ok=True)
    print(f"RESUME #{n} status={s['status']} step={step}\n{hint.replace('<n>', str(n))}")
    if step in ("code", "submit"):
        print()
        cmd_context(cfg, n)
    return step


def cmd_review_done(cfg, wf, n, fail=None):
    """Ghi nhận review 1 lượt SAU khi reviewer trả kết quả (resume dựa vào marker này); FAIL → rework."""
    gh.comment(cfg, n, f"<!-- omi:reviewed -->\n🔎 Review 1 lượt: {'FAIL — ' + fail if fail else 'PASS'}")
    if fail:
        cmd_rework(cfg, wf, n, f"Review: {fail}")
    print(f"REVIEWED #{n} {'FAIL' if fail else 'PASS'}")
```

- [ ] **Step 5: `skills/omi-status/SKILL.md`**

```markdown
---
name: omi-status
description: Xem tiến độ dự án omi (tỉ lệ Done, theo Epic/milestone, đang làm, Blocked, rework, task kế tiếp).
---

Chạy `OMI_CLI status` (thêm `--milestone <m>` nếu người dùng nêu) và trả lại **nguyên văn** output; không phân tích thêm trừ khi được hỏi. Nhắc một dòng: gõ `! <OMI_CLI> status` để xem mà không tốn token.
```

- [ ] **Step 6: `skills/omi-resume/SKILL.md`**

```markdown
---
name: omi-resume
description: Tiếp tục task omi còn dở của phiên trước (tạm dừng, chạm limit): script xác định bước tiếp theo rồi làm tiếp theo omi-implement.
---

`OMI_CLI` = lệnh ở dòng `OMI_CLI:` đầu phiên. Không đọc lại lịch sử phiên trước; trạng thái nằm trên GitHub + git + `.omi/tmp/`.

1. Đầu phiên đã có dòng `RESUME ...` (hook) → dùng luôn; nếu không: `OMI_CLI resume`.
2. Theo `step`:
   - `code`: `git -C <repo_dir> diff --stat` để biết phần đã làm, chỉ mở file liên quan; làm tiếp → `OMI_CLI check` → commit → bước 3 của omi-implement.
   - `submit`: `OMI_CLI check` → `OMI_CLI submit n` → bước 4 của omi-implement.
   - `review`: bước 4 của omi-implement với gói `.omi/tmp/review-n.md` (gợi ý nói mất gói → `OMI_CLI submit n` trước).
   - `qa`: `OMI_CLI qa n` → bước 5 của omi-implement.
   - `blocked`: báo người dùng lý do, dừng.
   - `start` / `next`: chạy omi-implement từ bước 1.
```

- [ ] **Step 7: Chạy test** — Run: `python -m unittest discover -s tests -v` — Expected: PASS.

- [ ] **Step 8: Thử trên sandbox**: giữa chừng một task (In Progress, có thay đổi chưa commit) đóng phiên Claude Code → mở phiên mới → dòng đầu có `RESUME #n status=In Progress step=code` kèm context; `! <OMI_CLI> status` in đúng số liệu Project.

- [ ] **Step 9: Commit** — `git add -A && git commit -m "feat: status, resume, review-done; skill omi-status, omi-resume"`

### Task 021: E2E sandbox, README, dogfood

**Files:**
- Create: `tests/e2e.sh`
- Modify: `README.md`

- [ ] **Step 1: Viết `tests/e2e.sh`**

```bash
#!/usr/bin/env bash
# E2E trên repo sandbox thuộc org, mô hình workspace: chạy trong thư mục workspace,
# clone sandbox (repo trống, đã có remote) nằm ở ./repo.
# Dùng: bash <omi-hub>/tests/e2e.sh <omi-hub>
set -euo pipefail
OMI="python $1/scripts/omi.py"
$OMI init --repo-dir repo --milestone "e2e" \
  --test-cmd "python -c \"import os,sys; sys.exit(not os.path.exists('e2e.txt'))\"" \
  --accept-cmd "python -c \"print('test_ac{n}_1 ok')\""

cat > /tmp/omi-e2e-plan.json <<'EOF'
{"milestone": "e2e", "items": [
  {"key": "E001", "type": "Epic", "title": "Kiểm thử e2e omi",
   "body": "### Mục tiêu\nXác nhận pipeline omi\n\n### Phạm vi\n- một story, một task", "children": [
    {"key": "E001.S001", "type": "User Story", "title": "Dev có thể chạy e2e",
     "body": "### Story\nLà dev, tôi muốn chạy e2e để kiểm tra omi.\n\n### Acceptance criteria\n- [ ] file e2e.txt tồn tại",
     "children": [
      {"key": "E001.S001.T001", "type": "Task", "title": "Tạo file e2e.txt",
       "body": "### Việc cần làm\nTạo e2e.txt\n\n### Definition of done\n- [ ] Test pass"}]}]}]}
EOF
$OMI plan-show /tmp/omi-e2e-plan.json
$OMI apply /tmp/omi-e2e-plan.json --approve
$OMI apply /tmp/omi-e2e-plan.json --approve   # idempotent: không tạo thêm
if $OMI new Task "x" --parent 1 2>/dev/null; then echo "template FAIL: title sai mẫu vẫn tạo được"; exit 1; fi

E=$($OMI tree | grep "Kiểm thử e2e omi" | sed -E 's/^ *#([0-9]+).*/\1/')
T=$($OMI start | grep -oE 'START #[0-9]+' | grep -oE '[0-9]+')
echo ok > repo/e2e.txt && git -C repo add e2e.txt && git -C repo commit -m "#$T: e2e"
test ! -e repo/AGENTS.md && test ! -e repo/.omi             # file agent/omi không lọt vào repo
$OMI check | grep -q "CHECK PASS"
SUB=$($OMI submit "$T"); echo "$SUB" | grep -q "reviewers=code"
PR=$(echo "$SUB" | grep -oE 'PR #[0-9]+' | grep -oE '[0-9]+')
$OMI pr-lint "$PR" | grep -q "PR OK"              # PR do script sinh đúng template
$OMI rework "$T" --reason "e2e rework"
$OMI submit "$T" | grep -q "reviewers=none"       # review LLM chỉ 1 lượt
$OMI qa "$T" | tee /tmp/omi-e2e-qa.out
grep -q "DONE #$T" /tmp/omi-e2e-qa.out
grep -q "ACCEPT PASS" /tmp/omi-e2e-qa.out
$OMI tree "$E" | grep -q "Kiểm thử e2e omi — Done" && echo "rollup OK"
$OMI audit && echo "audit OK"
```

- [ ] **Step 2: Chạy e2e** — Run: `bash <omi-hub>/tests/e2e.sh <omi-hub>` trong thư mục workspace có clone sandbox ở `./repo` — Expected: in `rollup OK`, `audit OK`; trên GitHub Task có `Rework Count = 1`, issue có đủ các mục template.

- [ ] **Step 3: Viết `README.md`**

````markdown
# omi-hub

Plugin Claude Code chuẩn hóa quy trình dự án trên GitHub Projects (gói free), tối ưu token:
mọi việc tất định do script làm; LLM chỉ phân rã PRD, viết code, review 1 lượt.

## Yêu cầu
- Repo thuộc GitHub Organization (dùng Issue Types)
- `gh` ≥ 2.60, đăng nhập với scope `project, repo, admin:org`
- Python ≥ 3.11

## Cài
```
/plugin marketplace add omi-home/omi-hub
/plugin install omi-hub@omi-home
```

## Dùng (`OMI_CLI` in ở dòng đầu mỗi phiên Claude Code)
1. Một lần mỗi org: `OMI_CLI init --template-only` → tạo views theo `docs/views.md`.
2. Mỗi dự án, từ thư mục workspace (repo là thư mục con): `OMI_CLI init --repo-dir <repo> --from-template <số project mẫu> --test-cmd "..." --accept-cmd "..."`, tạo secret `OMI_PROJECT_TOKEN`. `AGENTS.md`, `.claude/`, `.omi/` nằm ở workspace, không vào repo.
3. Backlog từ PRD: skill `omi-plan`.
4. Làm task: skill `omi-implement`; `/clear` giữa các task.
5. Change Request/Bug: skill `omi-change`.
6. Còn lại chạy thẳng, không tốn token: `OMI_CLI tree | next | template <type> | new | move | block | audit`.

Template từng loại: `scripts/templates.json` (sửa xong chạy lại `init` để sinh lại issue forms).
Thiết kế: `docs/specs/2026-11-24-omi-hub-design.md`.

## Phát triển
`python -m unittest discover -s tests -v` · E2E: `tests/e2e.sh` trên repo sandbox.
````

- [ ] **Step 4: Chạy toàn bộ unit test** — Run: `python -m unittest discover -s tests -v` — Expected: PASS.

- [ ] **Step 5: Commit** (hỏi người dùng trước khi tạo/push repo `omi-home/omi-hub`)

```bash
git add -A && git commit -m "test: e2e sandbox; docs: README"
```

- [ ] **Step 6: Dogfood**: chọn một repo thật của org, `OMI_CLI init`, `/omi-plan` với PRD thật, chạy `/omi-implement` cho 2–3 Task. Ghi lại các chỗ gây vướng thành issue trên chính repo `omi-hub` (dùng omi để quản lý omi).
