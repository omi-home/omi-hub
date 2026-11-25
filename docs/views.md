# 5 view của Project (init tạo, chỉnh tay group by/sort)

`omi init` (không `--from-template`) tự tạo 5 view dưới đây với layout + filter qua GraphQL. API chưa cho đặt group by/column by/sort/cột hiển thị theo tên field, nên chỉnh tay phần đó (Board mặc định chia cột theo Status):

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
