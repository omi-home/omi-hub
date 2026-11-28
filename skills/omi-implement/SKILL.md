---
name: omi-implement
description: Làm một Task/Bug omi tới Done (start → code → check → submit → review 1 lượt → qa).
---

`OMI_CLI` = lệnh ở dòng `OMI_CLI:` đầu phiên. Issue/GitHub Project chỉ thao tác qua `OMI_CLI`, không gọi `gh issue`/`gh project`/GraphQL trực tiếp (hook hỏi lại); thiếu lệnh/plugin chạy sai → báo người dùng, ghi `OMI_CLI feedback "<tóm tắt>"` (issue omi-hub), rồi làm tiếp phần khác. Bạn tự viết và tự sửa code trong phiên này; không giao code cho subagent.

1. Đầu phiên đã có dòng `RESUME` → làm theo skill omi-resume. Nếu không: `OMI_CLI start [n]` → `START #n` (hoặc `NONE`: báo và dừng), rồi `OMI_CLI context n`.
2. `context` có `## Findings mang theo` → làm các finding liên quan tới file đang sửa (không mở rộng phạm vi), nhớ mã `<p>.<i>`.
   TDD: test trước (Bug: test tái hiện; AC của parent #p: test tên chứa `ac<p>_<i>`), rồi code. Chỉ đọc file cần thiết. Lặp `OMI_CLI check` tới `CHECK PASS` (`CHECK WARN` = chưa có test-cmd, báo người dùng). Commit `#n: <tóm tắt>`. Trước bước dài (sửa nhiều file, chạy test lâu): `OMI_CLI handoff note --wip "<đang làm gì / bước kế>"` (hook tự checkpoint git/check sau mỗi tool call; phiên bị ngắt vì limit thì `resume` in lại).
3. `OMI_CLI submit n [--findings "<p>.<i>,..."]` (mã finding đã làm ở bước 2; luôn đặt trong ngoặc kép — PowerShell đổi `173.10` không ngoặc thành `173.1`; đánh nhầm → `OMI_CLI finding-reopen "<p>.<i>"`) → `REVIEW #n PR #pr pack=<f> reviewers=<...>`.
4. Nếu `reviewers` khác `none`: gọi song song subagent `omi-hub:omi-reviewer` và (nếu có `security`) `omi-hub:omi-security-reviewer`, prompt đúng một dòng `Pack: <f>`.
   - Mỗi `IMPROVE:` → thêm `--improve "<gợi ý>"` vào lệnh `review-done` bên dưới (script ghi vào findings của parent, task sau mang theo). Không làm trong task này; chỉ tạo Task riêng (`OMI_CLI new Task`) khi gợi ý vượt phạm vi Epic.
   - Không có `BLOCKER:` → `OMI_CLI review-done n [--improve "..."]...`.
   - `BLOCKER:` có vẻ sai (đọc nhầm diff, đã có test...) → báo người dùng kèm bằng chứng; **chỉ khi người dùng xác nhận** mới `OMI_CLI review-done n --override "<lý do>"` (PASS, không rework). Không tự override.
   - Có `BLOCKER:` → `OMI_CLI review-done n --fail "<blocker gộp ≤ 3 dòng>" [--improve "..."]...` (script ghi nhận + rework) → sửa → `check` → `submit n` (lần này `reviewers=none`, không review lại).
5. `OMI_CLI qa n`:
   - `QA FAIL ... log=<f> status=In Progress` → đọc log, sửa, `check`, `submit n`, `qa n`.
   - `QA INFRA <lý do>` → lỗi hạ tầng CI, không rework: báo người dùng, sửa cấu hình xong chạy lại `qa n`.
   - `status=Blocked` → dừng, báo người dùng (vượt 3 lần rework).
   - `DONE #n`. Nếu có `ACCEPT FAIL #p` với AC tự động → `OMI_CLI new Task "Đạt AC<i> của #p" --parent p --field "Việc cần làm=<nội dung AC>"`, `move` Ready, báo người dùng. AC `[manual]` → nhắc người dùng tick.
6. `qa`/`move ... Cancelled` tự cập nhật `.omi/HANDOFF.md` (không sửa tay mục tự động); chỉ ghi điều không suy ra được từ GitHub bằng `OMI_CLI handoff note "<text>"`. Báo một dòng: `#n Done · PR #pr · rework k · task mới: ...` và nhắc: "Gõ `/clear` rồi `tiếp` — hook tự nạp task kế tiếp".
