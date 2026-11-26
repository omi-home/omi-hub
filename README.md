# omi-hub

Plugin Claude Code chuẩn hóa quy trình dự án trên GitHub Projects (gói free), tối ưu token:
mọi việc tất định do script làm; LLM chỉ phân rã PRD, viết code, review 1 lượt.

## Yêu cầu
- Repo thuộc GitHub Organization (dùng Issue Types)
- `gh` ≥ 2.60, đăng nhập với scope `project, repo, admin:org`
- Python ≥ 3.11

## Cài
```
/plugin install omi-hub --marketplace omi-home/omi-hub
```
Claude Code cũ hơn 2.1.275: `/plugin marketplace add omi-home/omi-hub` rồi `/plugin install omi-hub@omi-home`.

## Dùng (`OMI_CLI` in ở dòng đầu mỗi phiên Claude Code)
1. Một lần mỗi org: `OMI_CLI init --template-only` → tạo views theo `docs/views.md`.
2. Mỗi dự án, từ thư mục workspace (repo là thư mục con): `OMI_CLI init --repo-dir <repo> --from-template <số project mẫu> --test-cmd "..." --accept-cmd "..."`, tạo secret `OMI_PROJECT_TOKEN`. `AGENTS.md`, `.claude/`, `.omi/` nằm ở workspace, không vào repo. init gộp `.claude/settings.json` để bật plugin cho mọi người mở workspace.
   Cập nhật plugin: `claude plugin marketplace update omi-home && claude plugin update omi-hub@omi-home`, khởi động lại, chạy lại `init` rồi `OMI_CLI doctor`.
3. Backlog từ PRD: skill `omi-plan`.
4. Làm task: skill `omi-implement`; `/clear` giữa các task (hook tự nạp task dở hoặc task kế tiếp; phiên bị ngắt → skill `omi-resume`).
   Quy tắc: repo cài omi-hub thao tác issue/GitHub Project chỉ qua `OMI_CLI` — hook SessionStart in dòng `QUY TẮC`, hook PreToolUse hỏi lại khi gọi `gh issue create|edit|delete|transfer`, `gh project item-*|field-*` hoặc mutation GraphQL tương ứng (chặn hẳn `gh issue close|reopen`, `gh project item-edit`). Thiếu lệnh → mở issue omi-hub.
   Gợi ý review (`IMPROVE`) không thành Task: `review-done n --improve "..."` ghi vào findings của parent, `context` của task sau hiện `## Findings mang theo`, làm xong báo `submit n --findings <p>.<i>`. Task Draft gợi ý kiểu cũ → `OMI_CLI carry <n>...`.
5. Change Request/Bug: skill `omi-change`.
6. Release: PR task vào `develop`; `OMI_CLI release` mở PR develop→main chờ PO approve (có ruleset thì tự merge, không thì `OMI_CLI release --merge`). PO = owner của org (team `org-owners`, tự đồng bộ); tác giả PR không tự approve được.
7. Còn lại chạy thẳng, không tốn token: `OMI_CLI status | tree | next | template <type> | new | move | block | audit | doctor | feedback` (doctor: kiểm workspace sau cập nhật plugin, FAIL kèm cách sửa; feedback: ghi bug/improvement plugin thành issue ở repo omi-hub).

Template từng loại: `scripts/omi_hub/config/templates.json` (sửa xong chạy lại `init` để sinh lại issue forms).
Thiết kế: [docs/specs/2026-11-24-omi-hub-design.md](docs/specs/2026-11-24-omi-hub-design.md).

## Phát triển
Release hub: tăng `version` trong `.claude-plugin/plugin.json` theo milestone (vd. v0.4.0 → `0.4.0`), merge rồi `claude plugin tag --push` trên main. Không tăng thì `claude plugin update` không nhận bản mới.

`python -m unittest discover -s tests -v` · E2E: `bash tests/e2e.sh <omi-hub>` trong workspace có clone sandbox ở `./repo`.
