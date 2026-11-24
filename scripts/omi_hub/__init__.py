"""omi-hub CLI core.

Layer (phụ thuộc chỉ đi vào trong):
- domain/          luật thuần, không I/O (lifecycle, rework, relations, guards, audit, ...)
- config/          dữ liệu khai báo (workflow.json, templates) + hàm nạp
- infrastructure/  adapter bên ngoài (gh CLI) — Task 007
- application/     use case điều phối domain + infrastructure — Task 010
- cli/             parse tham số, in output — Task 010
"""
