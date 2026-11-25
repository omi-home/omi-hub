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
   - Tài liệu kỹ thuật dùng chung (kiến trúc, quy ước, mô hình dữ liệu) ở `docs/` của repo: không chép vào body; ghi mục `### Tham chiếu` mỗi dòng một `docs/<file>.md#<anchor heading>` đúng phần node cần. `context` tự ghép đúng các mục đó (của Task và parent) cho agent.
   - Key phân cấp ổn định (`E001.S002.T003`). Key duy nhất trong cả repo: plan mới dùng số Epic chưa có (apply báo lỗi nếu key đã thuộc issue khác title). Gắn vào issue có sẵn: `"parent": <số>` ở node gốc. Milestone chỉ ở `plan.milestone` hoặc node gốc không có `parent` (con kế thừa); mỗi milestone khác nhau là một Epic gốc riêng; apply tự tạo milestone chưa có.
   - Phụ thuộc: `"blocked_by": ["<key>", <số issue>]` chỉ ở Task phải chờ (key trong plan này hoặc đã có trong repo, kể cả plan milestone trước). Story B phụ thuộc Story A → khai báo ở các Task của B. Chỉ khai báo thứ tự thực sự; `next` bỏ qua Task còn blocker mở; vòng lặp bị báo lỗi.

```json
{"milestone": "v1.0", "items": [
  {"key": "E001", "type": "Epic", "title": "Quản lý đơn hàng", "priority": "P1",
   "body": "### Mục tiêu\n...\n\n### Phạm vi\n- ...", "children": [
    {"key": "E001.S001", "type": "User Story", "title": "Khách hàng có thể đặt hàng", "estimate": 3,
     "body": "### Story\nLà khách, tôi muốn ... để ...\n\n### Acceptance criteria\n- [ ] ...", "children": [
      {"key": "E001.S001.T001", "type": "Task", "title": "Thêm API POST /orders",
       "body": "### Việc cần làm\n...\n\n### Definition of done\n- [ ] Test pass"},
      {"key": "E001.S001.T002", "type": "Task", "title": "Thêm form đặt hàng", "blocked_by": ["E001.S001.T001"],
       "body": "### Việc cần làm\n...\n\n### Definition of done\n- [ ] Test pass"}]}]}]}
```
3. `OMI_CLI plan-show <file>`: lỗi → sửa file, chạy lại. Hợp lệ → báo người dùng đường dẫn file và bảo họ xem output cây (không chép lại cây).
4. Người dùng đồng ý (= chốt baseline) → `OMI_CLI apply <file> --approve`; chỉ muốn nháp → `OMI_CLI apply <file>`. Chạy lại apply an toàn (bỏ qua key đã có).
