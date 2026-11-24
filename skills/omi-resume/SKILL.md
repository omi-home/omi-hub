---
name: omi-resume
description: "Tiếp tục task omi còn dở của phiên trước (tạm dừng, chạm limit): script xác định bước tiếp theo rồi làm tiếp theo omi-implement."
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
