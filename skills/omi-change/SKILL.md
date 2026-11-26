---
name: omi-change
description: Tạo và xử lý Change Request (đổi yêu cầu đã Approved) hoặc Bug (lỗi trên item đã Done) trong repo omi.
---

`OMI_CLI` = lệnh ở dòng `OMI_CLI:` đầu phiên. Không đọc code trừ khi người dùng yêu cầu.

## Change Request
1. `OMI_CLI new "Change Request" "Thay đổi <đối tượng>: <tóm tắt>" --parent <epic> --affects <a,b> --field "Lý do thay đổi=..." --field "Nội dung thay đổi=<trước → sau>"` (khung đầy đủ: `OMI_CLI template "Change Request"`).
2. `OMI_CLI impact <cr> --post` (script liệt kê item bị ảnh hưởng và item con).
3. Chỉ dựa trên danh sách đó, đề xuất cho người dùng: Task cần thêm (tiêu đề một dòng, parent), Task cần hủy.
4. Người dùng đồng ý → `OMI_CLI move <cr> Approved`; sửa yêu cầu của item bị ảnh hưởng: `OMI_CLI edit <a> --field "Mục=nội dung mới" --cr <cr>` (không sửa body bằng `gh`); `OMI_CLI new Task "<động từ> <đối tượng>" --parent <cr> --field "Việc cần làm=..." [--blocked-by <n>]...` rồi `move <task> Ready` (còn blocker mở → tự Waiting); hủy: `OMI_CLI move <task> Cancelled --reason "Thay bởi Change Request #<cr>"`. Từ chối → `OMI_CLI move <cr> Cancelled --reason "<lý do>"`.
5. Làm các Task bằng skill omi-implement. Change Request tự Done khi Task xong.

## Bug
1. `OMI_CLI new Bug "<thành phần>: <triệu chứng>" --affects <n> --milestone <m> --field "Các bước tái hiện=..." --field "Kết quả mong đợi=..." --field "Kết quả thực tế=..."` (khung: `OMI_CLI template Bug`).
2. Bước tái hiện rõ ràng → `OMI_CLI move <bug> Ready`. Không phải lỗi/trùng → `OMI_CLI move <bug> Cancelled --reason "..."`.
3. Sửa bằng skill omi-implement (bước đầu: viết test tái hiện fail).
