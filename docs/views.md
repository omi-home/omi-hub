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
