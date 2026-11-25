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
3. Backlog từ PRD: skill `omi-plan`.
4. Làm task: skill `omi-implement`; `/clear` giữa các task (hook tự nạp task dở hoặc task kế tiếp; phiên bị ngắt → skill `omi-resume`).
5. Change Request/Bug: skill `omi-change`.
6. Release: PR task vào `develop`; `OMI_CLI release` mở PR develop→main chờ PO approve (có ruleset thì tự merge, không thì `OMI_CLI release --merge`). PO = owner của org (team `org-owners`, tự đồng bộ); tác giả PR không tự approve được.
7. Còn lại chạy thẳng, không tốn token: `OMI_CLI status | tree | next | template <type> | new | move | block | audit`.

Template từng loại: `scripts/omi_hub/config/templates.json` (sửa xong chạy lại `init` để sinh lại issue forms).
Thiết kế: [docs/specs/2026-11-24-omi-hub-design.md](docs/specs/2026-11-24-omi-hub-design.md).

## Phát triển
`python -m unittest discover -s tests -v` · E2E: `bash tests/e2e.sh <omi-hub>` trong workspace có clone sandbox ở `./repo`.
