# Spike results (2026-11-24)

Sandbox: `omi-home/omi-sandbox` (private, giữ lại cho e2e), Project thử `omi spike` (#9). gh CLI, Claude Code 2.1.325.

| # | Giả định | Kết quả | Quyết định |
|---|---|---|---|
| 1 | REST issue-types list/create | ✓ list trả 8 type; POST trả id; DELETE ✓ | Giữ nguyên |
| 2 | Tạo issue với `type` (REST) | ✓ `-f type=Task`; `PATCH -f type=Bug` đổi type ✓ | Giữ nguyên |
| 3 | sub_issues POST + GraphQL parent/subIssues | ✓ 201; `parent.number`, `subIssues.nodes` đúng | Giữ nguyên |
| 4 | dependencies/blocked_by + GraphQL blockedBy | ✓ 201; `blockedBy.nodes[0].state = OPEN` | Giữ nguyên |
| 5 | GraphQL closedByPullRequestsReferences | ✓ PR `Closes #2` → `{number, state: OPEN, merged: false}`. `SNAPSHOT_QUERY` chạy nguyên văn không lỗi field | Giữ nguyên query Task 007 |
| 6 | Project có cột Type | ✗ `gh project field-list` và GraphQL `fields { dataType }` đều không có field Type (chỉ Title, Assignees, Status, Labels, Linked PRs, Milestone, Repository, Reviewers, Parent issue, Sub-issues progress, Created/Updated/Closed) | Như ghi nhận khởi tạo: không dựa vào field Type; type lấy từ `issueType` của issue |
| 7 | updateProjectV2Field options Status | ✓ 10 option đúng thứ tự | Giữ nguyên `UPDATE_STATUS` |
| 8 | project copy giữ views/workflows | ◐ Bản copy giữ Status 10 options, các view (kể cả `Board` tự tạo) và workflow `Auto-add sub-issues to project`. **Không giữ** workflow `Auto-add to project` (bản gốc bật, bản copy không có trong danh sách workflows). View tạo được bằng REST `POST orgs/{org}/projectsV2/{n}/views` (`name`, `layout=board`); workflow không có API | Giữ `gh project copy`; view thiếu → tạo bằng REST. Không dựa vào Auto-add: omi tự thêm item (`add_to_project`, Task 007); `init` in hướng dẫn bật Auto-add trên UI nếu muốn |
| 9 | --paginate --slurp | ✓ trả `[[...],[...]]` (per_page=1, 2 trang). **Không dùng chung với `--jq`** (gh báo lỗi) | Parse JSON trong Python, không truyền `--jq` khi `--slurp` |
| 10 | Issue form `type:` | ✓ Issue #5 tạo từ form `task.yml` (`type: "Task"`) có type Task; event `issues: typed` cũng bắn khi tạo từ form | Giữ nguyên (Task 011) |
| 11 | Action `issues: typed` | ✓ đổi type #1, #3 bằng REST → 2 run `issues` success | Giữ nguyên |
| 12 | CLAUDE_PLUGIN_ROOT trong hook | ✓ `ROOT=<thư mục plugin>` (đường dẫn dạng `C:/...` dấu `/`) | Giữ nguyên |
| 13 | agent memory: project trong plugin | ✓ nhưng thư mục là `.claude/agent-memory/<plugin>-<agent>/` (ví dụ `probe-probe/`), agent gọi bằng `probe:probe` | Spec D9 sửa đường dẫn (`omi-hub-omi-reviewer/`); skill gọi reviewer bằng `omi-hub:omi-reviewer` |
| 14 | Issue Type tên dài có dấu cách/gạch ngang tạo + gán + filter `type:"..."` | ✓ "Spike Non-Functional Requirement": tạo, gán qua REST, `gh issue list --search 'type:"..."'` trả đúng issue | Giữ nguyên |
| 15 | Fine-grained PAT (`OMI_PROJECT_TOKEN`) đọc/ghi Project v2 của org | ✓ Trong Action: `field-list`, `item-add`, `item-edit` Status=Ready OK. Chỉ có org Projects RW + repo Issues RW thì **lỗi** `Resource not accessible by personal access token (...pullRequests...)` (field-list/snapshot đọc PR liên kết) | Quyền PAT: org Projects RW; repo Issues RW, **Pull requests R** (+ Contents R cho repo omi-hub). Đã sửa checklist `init` trong plan |

## Phát hiện thêm

- Khi mở PR `Closes #2`, Status của item #2 trong Project tự thành `In Review` dù mọi built-in workflow về PR đang tắt. → `submit` phải chấp nhận Status đã là `In Review` (ghi lại không lỗi); `audit` không coi đây là vi phạm.
- `gh repo clone` mặc định SSH có thể lỗi trên máy không có SSH key; dùng `git clone https://...` khi cần.
