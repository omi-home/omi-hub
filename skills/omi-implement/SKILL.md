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
