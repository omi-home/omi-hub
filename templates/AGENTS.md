<!-- omi:begin -->
## omi-hub
Dự án quản lý bằng omi-hub (GitHub Project). `OMI_CLI` = lệnh ở dòng `OMI_CLI:` đầu phiên. CLI tự kiểm luật và in lý do khi từ chối.
- **Script-first (ưu tiên hàng đầu với mọi yêu cầu):** trước tiên tìm lệnh `OMI_CLI`/script làm được; LLM chỉ làm việc cần phán đoán; việc lặp lại chưa có script → đề xuất viết script trước.
- Đổi status chỉ qua `OMI_CLI move|rework|block|unblock` (không `gh issue close`, `gh project item-edit`).
- `Approved` chỉ khi người dùng xác nhận.
- Lỗi khi đang làm → `rework`; lỗi trên item đã Done → `new Bug --affects`; đổi yêu cầu đã Approved → skill omi-change.
- Test nghiệm thu: AC thứ i của issue #p ↔ test có tên chứa `ac<p>_<i>`; AC không tự động hóa được ghi `[manual]`.
- Mỗi loại có template chuẩn: title có prefix đầy đủ (`[Functional Requirement] ...`, CLI tự thêm) + body theo `OMI_CLI template <type>`; tạo nhanh bằng `new ... --field "Mục=nội dung"`. PR do `submit` sinh theo template PR. CLI từ chối sai mẫu.
- Làm task: skill omi-implement. Lập backlog từ PRD: skill omi-plan.
- Lệnh: next · tree [n] · context n · start [n] · check · submit n · qa n · accept n · new · move · rework · block · unblock · impact · audit
<!-- omi:end -->
