# omi-hub — Thiết kế plugin Claude Code quản lý dự án trên GitHub Projects

- Ngày: 2026-11-24
- Trạng thái: Đang review
- Ngôn ngữ triển khai: Python 3.11+ (chỉ stdlib) + `gh` CLI

## 1. Mục tiêu

Chuẩn hóa quy trình triển khai dự án với Claude Code trên GitHub Projects (gói free) để mỗi dự án mới **không phải setup lại** GitHub Project, issue types, fields, views, templates, skills, memory.

Thành công khi:

1. Một lệnh `OMI_CLI init` biến một repo trống của org thành repo có đầy đủ cấu trúc quản lý chuẩn.
2. Từ một PRD, Claude sinh được cây work item đúng quan hệ và tạo lên GitHub sau khi người duyệt.
3. Claude tự chạy vòng implement Task → Review → QA → Done, cập nhật status đúng lifecycle, ghi nhận rework, không tạo item trùng.
4. Status sai quy tắc bị chặn trong Claude Code và bị phát hiện (audit) khi sửa tay trên web.

Ngoài phạm vi v1: tài khoản cá nhân (không có Issue Types), một Project cho nhiều repo, báo cáo/biểu đồ, tích hợp ngoài GitHub.

## 2. Quyết định đã chốt

| # | Quyết định | Lý do |
|---|---|---|
| D1 | Repo thuộc **Organization**, Work Item Type = **Issue Types gốc** | Hiển thị trên issue, filter `type:`; Project không có field Type qua API → omi đọc `issueType` của issue |
| D2 | **Một** trường `Status` chung (hợp các trạng thái), plugin ràng buộc theo loại | Project chỉ có 1 Status; board/view và built-in automation dùng chung được |
| D3 | Thực thi rule ở **plugin** (chặn) + **GitHub Action** (audit) | Claude không đi tắt được; sửa tay trên web vẫn được phát hiện |
| D4 | **1 Project / 1 repo** | Khớp với Milestone (cấp repo) |
| D5 | Python **stdlib** + subprocess `gh` | Không cần cài đặt; xác thực dùng `gh auth` |
| D6 | Vòng implement **tự động hoàn toàn** (kể cả merge), phanh an toàn: rework > 3 → Blocked. Review = **code review LLM đúng 1 lượt** + **security review LLM 1 lượt khi script phát hiện** task chạm security; **không có vòng review thứ hai** (script thực thi: chỉ `submit` đầu tiên yêu cầu review); gợi ý cải tiến thành **finding** trên comment `<!-- omi:findings -->` của parent (`review-done --improve`), task sau mang theo qua `context` và báo xong bằng `submit --findings`, không chặn. QA Task/Bug = **script** (test + CI). Nghiệm thu Story/Functional Requirement/Non-Functional Requirement = **script** (mỗi AC ↔ một test tên `ac<số issue>_<thứ tự>`) | Theo yêu cầu; phanh tránh vòng lặp vô hạn |
| D7 | Chốt baseline (`Approved`) cho Epic/Story/Functional Requirement/Non-Functional Requirement/Change Request **luôn do người** | Baseline là cam kết; Change Request chỉ có nghĩa khi baseline do người chốt |
| D8 | `AGENTS.md` là file hướng dẫn agent duy nhất (Claude Code nạp trực tiếp), **không** tạo `CLAUDE.md` | Theo yêu cầu |
| D9 | Memory dùng cơ chế gốc: subagent `memory: project` → `.claude/agent-memory/<plugin>-<agent>/` (vd. `omi-hub-omi-reviewer/`) | Không tự chế memory |
| D10 | **Script-first, ưu tiên hàng đầu với mọi yêu cầu mới: việc gì script làm được thì không dùng LLM** (mục 2.1) | Theo yêu cầu; tối ưu token |
| D12 | **Mô hình workspace**: `AGENTS.md`, `.claude/`, `.omi/` ở thư mục workspace; repo git là thư mục con, chỉ chứa code/docs/`.github/` (mục 5.4) | Tách công cụ agent khỏi mã sản phẩm |
| D13 | **Nhánh develop mặc định cho mọi project**: develop là default branch, PR task vào develop; nhánh chính chỉ nhận PR release develop→main (merge commit) khi PO approve. **PO = owner của org** (không gắn cứng login): team `org-owners` đồng bộ từ org owner, ép buộc bằng ruleset + CODEOWNERS `* @<org>/org-owners` (tác giả PR không tự approve được); repo không có ruleset (private gói Free) thì chỉ `release --merge` kiểm | Theo yêu cầu; develop là default nên `issue develop`, `pr create`, `Closes #n` không đổi |
| D11 | **Phiên chính tự viết code và tự sửa** (không tách subagent viết code). Ngữ cảnh mới mỗi task bằng `/clear` + `context N` | Tách vai trò làm mất ngữ cảnh ở mỗi lần chuyển việc → đọc lại codebase, review không hội tụ, rework dây chuyền; thực tế tốn quota hơn |

### 2.1 Phân bổ LLM và script

LLM chỉ làm 5 việc cần phán đoán: (1) phân rã PRD thành plan JSON, (2) viết code + test (phiên chính), (3) code review 1 lượt, (4) security review 1 lượt khi script yêu cầu, (5) quyết định Task cho Change Request. Mọi việc còn lại là script:

| Việc | Ai làm | Lệnh |
|---|---|---|
| Bootstrap, xem cây, chọn việc, đổi status, audit | Script — người chạy thẳng trong terminal hoặc `!` trong Claude Code (0 token) | `init`, `tree`, `next`, `move`, `audit` |
| Gom ngữ cảnh cho LLM (issue, AC parent, Affects) | Script, một lần, output gọn | `context` |
| Ready → In Progress → checkout branch | Script | `start` |
| Lint, typecheck, quét secret/SAST, test cục bộ | Script, output 1 dòng khi pass, 60 dòng cuối khi fail | `check` |
| Push → PR → In Review → gói review (diff + AC) → quyết định có review/security review (chỉ lần submit đầu) | Script | `submit` |
| In QA → test + CI → merge → Done → rollup → nghiệm thu parent | Script; fail thì tự rework và ghi log ra file | `qa` |
| Nghiệm thu Story/Functional Requirement/Non-Functional Requirement theo AC | Script | `accept` |
| Liệt kê item bị ảnh hưởng của Change Request | Script | `impact` |
| Kiểm tra + vẽ cây plan | Script | `plan-show` |

Quy tắc giảm token cố định:

- 3 skill làm việc cần LLM (`omi-plan`, `omi-implement`, `omi-change`) + 2 skill mỏng chỉ gọi script (`omi-status`, `omi-resume`); mô tả mỗi skill một dòng. Thao tác thường ngày không cần skill (`! <OMI_CLI> ...` = 0 token).
- Mục omi trong `AGENTS.md` ≤ 15 dòng; luật nằm trong script, không lặp lại trong prompt.
- SessionStart in đúng 1 dòng.
- Output CLI dạng một dòng có tiền tố máy đọc được (`START`, `CHECK PASS`, `REVIEW`, `QA FAIL`...); log dài ghi ra `.omi/tmp/` và chỉ in đường dẫn.
- Subagent review đọc gói chuẩn bị sẵn (file), không tự đi khám phá repo, chỉ báo blocker theo checklist cố định.
- Một agent một task: không chuyển giao giữa các agent trong lúc viết/sửa code.

### 2.2 Chống rework dây chuyền

| Nguyên nhân thường gặp | Biện pháp |
|---|---|
| Review LLM tìm thêm vấn đề mới ở mỗi vòng | Review đúng 1 lượt/task; sau khi sửa chỉ chạy lại `check` (script) |
| Reviewer "khó tính" với lỗi máy bắt được | `check` chạy lint/typecheck/scan/test trước; reviewer bỏ qua phong cách và lỗi công cụ đã bắt |
| Gợi ý cải tiến bị coi là blocker | Reviewer tách `IMPROVE:`; phiên chính ghi finding vào parent (`review-done --improve`), task hiện tại đi tiếp; Task Draft gợi ý kiểu cũ → `carry` |
| Security review chung chung | Chỉ khi script phát hiện; checklist cụ thể (injection, authz, secret, crypto, input validation); phải chỉ ra dòng cụ thể |
| Người sửa không có ngữ cảnh | Cùng phiên vừa viết vừa sửa |
| Sửa xong vẫn fail | `qa` fail → rework; rework > 3 → Blocked, người quyết |

## 3. Mô hình dữ liệu

### 3.1 Work Item Types (Issue Types của org)

`Epic`, `User Story` (legacy), `Functional Requirement`, `Non-Functional Requirement`, `Change Request`, `Task`, `Bug`. **User Story là loại legacy** (CR #116): issue đã có vẫn hợp lệ với audit, rollup, accept, tree, status và vẫn làm parent được; `new`/`apply` không tạo mới, `init` không sinh issue form. Yêu cầu từ góc nhìn vai trò viết thành Functional Requirement có mục `### Story`. Bootstrap tạo loại còn thiếu, giữ nguyên các loại org đã có (`Feature` mặc định của GitHub không dùng; không xóa).

Không dùng label để phân loại. Label chỉ dành cho mục đích phụ (area, tech) nếu dự án muốn.

### 3.2 Quan hệ

| Loại | Vai trò | Parent (sub-issue) hợp lệ | Ràng buộc |
|---|---|---|---|
| Epic | Capability/feature lớn | — | Bắt buộc có Milestone |
| User Story (legacy) | Giá trị người dùng — chỉ issue cũ | Epic | Bắt buộc parent; không tạo mới |
| Functional Requirement | Yêu cầu chức năng | Epic, User Story | Bắt buộc parent |
| Non-Functional Requirement | Yêu cầu phi chức năng | Epic, User Story, Functional Requirement | Bắt buộc parent |
| Change Request | Thay đổi baseline | Epic | Bắt buộc parent, ≥1 `Affects` |
| Task | Công việc triển khai | User Story, Functional Requirement, Non-Functional Requirement, Change Request | Bắt buộc parent |
| Bug | Lỗi | — | ≥1 `Affects`, bắt buộc Milestone |

Cơ chế GitHub dùng:

- **Parent/child** → sub-issues gốc (giới hạn GitHub: 8 cấp, 100 con/parent; cây sâu nhất ở đây là Epic→Story→Functional Requirement→Non-Functional Requirement→Task = 5 cấp).
- **Affects** (Change Request, Bug) → mục `### Affects` trong body chứa `#12 #15`. GitHub tự tạo cross-reference trên item bị ảnh hưởng. Plugin kiểm tra các số tồn tại.
- **Blocked by** → Issue dependencies gốc.
- **Milestone** → chỉ đặt bắt buộc cho Epic và Bug; item con **kế thừa** milestone của Epic tổ tiên khi tạo. Audit phát hiện lệch. Milestone không phải parent của Epic.

### 3.3 Trường của Project

| Trường | Kiểu | Ghi chú |
|---|---|---|
| Status | single-select (gốc) | 11 giá trị, mục 4 |
| Type | gốc (issue type) | Không tạo trường trùng (spike xác nhận, xem 9) |
| Priority | single-select | P0, P1, P2, P3 |
| Estimate | number | Story point hoặc giờ, tùy dự án |
| Rework Count | number | Plugin tự tăng |
| Blocked Reason | text | Bắt buộc khi Blocked mà không có blocked-by |
| Parent issue, Sub-issues progress, Milestone | gốc | Dùng cho view |

### 3.4 Views (trong Project mẫu)

1. **Board** — group theo Status, filter `-status:Done,Cancelled`.
2. **Hierarchy** — table, group theo Parent issue, hiển thị Sub-issues progress.
3. **Requirements** — filter `type:"User Story","Functional Requirement","Non-Functional Requirement","Change Request"`.
4. **Delivery** — table filter `type:Task,Bug`, group theo Milestone, sort Priority.
5. **Blocked & Rework** — filter `status:Blocked` (filter Project không OR được giữa hai field; sort theo Rework Count chỉnh tay).

### 3.5 Metadata do plugin ghi trong body/comment

- `<!-- omi:key=E001.S002.T003 -->` trong body: khóa idempotent khi tạo từ plan.
- `<!-- omi:blocked-from=<Status> -->` trong comment khi block: để unblock về đúng trạng thái cũ.
- `<!-- omi:rework n=2 stage=review -->` trong comment rework.
- `<!-- omi:reviewed -->` trong comment do `review-done` ghi sau khi reviewer trả kết quả: không review lại; `resume` dựa vào marker này.
- `<!-- omi:impact -->` trong comment phân tích ảnh hưởng Change Request.

### 3.6 Template chuẩn cho từng loại

Nguồn duy nhất: `scripts/omi_hub/config/templates.json`. Từ đó script **sinh** issue forms (`.github/ISSUE_TEMPLATE/<type>.yml`), **in khung** (`template <type>`) và **kiểm tra** title + body khi `new`, `apply`, `plan-show`. Sửa template = sửa một file JSON, chạy lại `init` để sinh lại forms.

| Loại | Title (regex kiểm tra · ví dụ) | Mục body (★ = bắt buộc) |
|---|---|---|
| Epic | ≥ 5 ký tự · "Quản lý đơn hàng" | ★Mục tiêu · ★Phạm vi · Ngoài phạm vi · Chỉ số thành công |
| User Story | `<vai trò> có thể <hành động>` · "Khách hàng có thể theo dõi đơn hàng" | ★Story (`Là ..., tôi muốn ... để ...`) · ★Acceptance criteria (checklist) · Ghi chú |
| Functional Requirement | `Hệ thống phải\|cần <hành vi>` hoặc `<vai trò> có thể <hành động>` · "Hệ thống phải gửi email xác nhận đơn" | ★Mô tả · Story (`Là ..., tôi muốn ... để ...`) · ★Acceptance criteria (checklist) · Ràng buộc |
| Non-Functional Requirement | `<Nhóm>: <chỉ số> <ngưỡng>` · "Performance: p95 API đặt hàng < 300ms ở 100 RPS" | ★Nhóm (Performance/Security/Reliability/Usability/Maintainability/Compliance/Observability/Accessibility/Capacity) · ★Chỉ số và ngưỡng · ★Cách đo · ★Acceptance criteria |
| Change Request | `Thay đổi <đối tượng>: <tóm tắt>` · "Thay đổi thanh toán: hỗ trợ trả góp" | ★Lý do thay đổi · ★Nội dung thay đổi · ★Affects (`#n`) · Ảnh hưởng dự kiến |
| Task | ≥ 5 ký tự, `<động từ> <đối tượng>` · "Thêm API POST /orders" | ★Việc cần làm · ★Definition of done (checklist) · Ghi chú kỹ thuật |
| Bug | `<thành phần>: <triệu chứng>` · "Giỏ hàng: tổng tiền sai khi áp mã giảm giá" | ★Affects (`#n`) · Môi trường · ★Các bước tái hiện · ★Kết quả mong đợi · ★Kết quả thực tế |

**Prefix title** (viết đầy đủ, không viết tắt): `[Epic]`, `[User Story]`, `[Functional Requirement]`, `[Non-Functional Requirement]`, `[Change Request]`, `[Task]`, `[Bug]`. Ví dụ: `[Functional Requirement] Hệ thống phải gửi email xác nhận đơn`. Prefix = `[<tên Issue Type>] ` suy ra từ tên loại (không khai báo lặp). CLI (`new`, `apply`) tự thêm prefix nếu thiếu; issue form điền sẵn prefix; regex title áp cho phần sau prefix.

**Key work item trong plan**: `<chữ loại><NNN>` nối bằng dấu chấm theo cây — `E001`, `E001.S002`, `E001.S002.T003` (E=Epic, S=User Story, F=Functional Requirement, N=Non-Functional Requirement, T=Task, B=Bug); `validate_plan` từ chối key sai định dạng hoặc sai chữ loại.

Mục tùy chọn `Tham chiếu` (User Story, Functional Requirement, Non-Functional Requirement, Change Request, Task, Bug): mỗi dòng `docs/<file>.md#<anchor>`; tài liệu kỹ thuật dùng chung nằm ở `docs/` của repo, issue chỉ trỏ tới đúng mục.

Quy tắc kiểm tra: mục bắt buộc phải có heading `### <tên>` và nội dung khác giá trị mặc định / `_No response_`; mục checklist phải có ít nhất một dòng `- [ ] ...`; mục có danh sách lựa chọn phải đúng một lựa chọn; mục Affects phải chứa `#<số>`; HTML comment (gợi ý) không tính là nội dung. Audit không kiểm template issue (forms + CLI đã chặn lúc tạo).

### 3.7 Template PR

Nguồn: `scripts/omi_hub/config/pr_template.json`.

- **Title**: `<title issue, gồm prefix> (#<số issue>)`, ví dụ `[Task] Thêm API POST /orders (#12)`. Squash merge dùng title này làm commit message.
- **Body** (★ bắt buộc): ★Liên kết (`Closes #n`, Parent) · ★Thay đổi · Acceptance criteria liên quan (AC của parent ↔ test `ac<p>_<i>`) · ★Kiểm thử (checklist) · ★Security (`Không chạm security` | `Có chạm security`).
- `submit` **sinh title + body bằng script** từ issue, parent, `git log`, kết quả quét security — không tốn token.
- `init` sinh `.github/pull_request_template.md` cho PR tạo tay (gợi ý nằm trong comment, chưa điền = trống).
- `pr-lint N` kiểm title + body; GitHub Action chạy khi PR `opened/edited/synchronize/reopened`, fail thì check đỏ.

## 4. Status và lifecycle

### 4.1 Tập Status chung

`Draft` · `Triage` · `Approved` · `Waiting` · `Ready` · `In Progress` · `In Review` · `In QA` · `Blocked` · `Done` · `Cancelled`

Trạng thái kết thúc: `Done` (issue đóng *completed*), `Cancelled` (issue đóng *not planned*). Mọi trạng thái khác: issue mở.

### 4.2 Status hợp lệ theo loại

| Loại | Trạng thái khởi tạo | Status được dùng |
|---|---|---|
| Epic | Draft | Draft, Approved, In Progress, Blocked, Done, Cancelled |
| User Story / Functional Requirement / Non-Functional Requirement | Draft | Draft, Approved, In Progress, In QA, Blocked, Done, Cancelled |
| Change Request | Triage | Triage, Approved, In Progress, Blocked, Done, Cancelled |
| Task | Draft | Draft, Waiting, Ready, In Progress, In Review, In QA, Blocked, Done, Cancelled |
| Bug | Triage | Triage, Waiting, Ready, In Progress, In Review, In QA, Blocked, Done, Cancelled |

### 4.3 Transitions

Ký hiệu: **H** = cần người xác nhận (hook `ask`), **A** = plugin tự chuyển (rollup), **G** = có guard (mục 4.4).

**Epic**

| Từ | Sang | Ghi chú |
|---|---|---|
| Draft | Approved | H |
| Approved | In Progress | A khi con đầu tiên vào In Progress |
| In Progress | Done | A khi mọi con kết thúc và ≥1 con Done |
| Draft, Approved | Cancelled | G lý do |
| In Progress | Cancelled | G lý do, mọi con đã kết thúc |

**User Story / Functional Requirement / Non-Functional Requirement**

| Từ | Sang | Ghi chú |
|---|---|---|
| Draft | Approved | H |
| Approved | In Progress | A khi con đầu tiên vào In Progress |
| In Progress | In QA | A khi mọi con kết thúc |
| In QA | Done | QA nghiệm thu acceptance criteria đạt và mọi con đã kết thúc (guard `children_terminal`) |
| In QA | In Progress | Rework (QA không đạt) → tạo Task bổ sung dưới item này |
| Draft, Approved | Cancelled | G lý do |

Không có Approved → Draft: thay đổi baseline đã chốt phải đi qua Change Request.

**Change Request**

| Từ | Sang | Ghi chú |
|---|---|---|
| Triage | Approved | H; G phải có comment phân tích ảnh hưởng |
| Triage | Cancelled | G lý do (bị từ chối) |
| Approved | In Progress | A khi Task con đầu tiên vào In Progress |
| In Progress | Done | A khi mọi Task con kết thúc → plugin comment changelog vào các item Affects |

**Task**

| Từ | Sang | Ghi chú |
|---|---|---|
| Draft | Ready | G parent ở Approved hoặc In Progress, không còn blocked-by mở (còn → tự chuyển Waiting) |
| Draft, Ready | Waiting | G parent ở Approved hoặc In Progress (từ Draft), ≥1 blocked-by mở; `apply` tự chuyển Task Ready có blocker |
| Waiting | Ready | A khi issue blocked-by cuối cùng kết thúc (Done/Cancelled); G không còn blocked-by mở |
| Ready | In Progress | G không còn blocked-by mở; tự assign, tạo branch |
| In Progress | In Review | G có PR mở liên kết (`Closes #n`) |
| In Review | In QA | Review đạt |
| In Review, In QA | In Progress | Rework (lệnh `rework`) |
| In QA | Done | G PR đã merge |
| Draft, Waiting, Ready, In Progress | Cancelled | G lý do |

**Bug**: như Task, thay `Draft → Ready` bằng `Triage → Ready` (đã tái hiện được) và `Triage → Cancelled` (không phải lỗi/trùng, G lý do).

**Waiting vs Blocked**: Waiting = chờ phụ thuộc đã lên kế hoạch (blocked-by), script tự vào/ra, không cần người; chỉ Task/Bug (container giữ Approved, trạng thái do rollup từ con). Blocked = cần người can thiệp.

**Blocked (mọi loại)**: `X → Blocked` với X là trạng thái chưa kết thúc, G có `Blocked Reason` hoặc ≥1 blocked-by mở. `Blocked → X` chỉ về đúng trạng thái trước khi block.

`Done`, `Cancelled` là kết thúc, không mở lại. Lỗi phát hiện sau khi Done → tạo **Bug** `Affects` item đó. Lỗi phát hiện trước khi Done → **rework**, không tạo item mới.

### 4.4 Guards

| Guard | Kiểm tra |
|---|---|
| reason | Có `--reason` không rỗng (ghi thành comment) |
| parent_ready | Parent ở Approved hoặc In Progress |
| no_open_blockers | Không có blocked-by đang mở |
| has_open_blockers | Có ≥1 blocked-by đang mở |
| pr_open | Có PR mở với `Closes #n` trỏ tới issue |
| pr_merged | PR liên kết đã merge |
| children_terminal | Mọi sub-issue ở Done/Cancelled |
| impact_analysis | Change Request có comment chứa `<!-- omi:impact -->` |
| blocker_present | Có Blocked Reason hoặc blocked-by mở |

### 4.5 Rework

`omi rework #n --reason "..."` (chỉ từ In Review hoặc In QA):

1. Status → In Progress.
2. `Rework Count` += 1.
3. Comment `<!-- omi:rework n=<count> stage=<review|qa> -->` + lý do.
4. Nếu `Rework Count` > `max_rework` (mặc định 3) → Blocked với reason "Vượt giới hạn rework, cần người xem". Đây là phanh an toàn cho chế độ tự động hoàn toàn.

### 4.6 Rollup

Sau mỗi lần chuyển status của item X, plugin đánh giá parent P của X (đệ quy lên trên):

- X vào In Progress và P ở Approved → P chuyển In Progress.
- Mọi con của P kết thúc:
  - P là Story/Functional Requirement/Non-Functional Requirement → In QA (Claude chạy QA nghiệm thu).
  - P là Epic hoặc Change Request → Done (nếu ≥1 con Done, ngược lại không tự chuyển, báo người).
- Khi mọi issue của Milestone đóng → plugin báo "milestone sẵn sàng release", **không** tự đóng milestone.

## 5. Kiến trúc plugin

### 5.1 Cấu trúc thư mục

```
omi-hub/
  .claude-plugin/
    plugin.json
    marketplace.json
  skills/
    omi-plan/SKILL.md
    omi-implement/SKILL.md
    omi-change/SKILL.md     # Change Request + Bug
    omi-status/SKILL.md     # mỏng: OMI_CLI status
    omi-resume/SKILL.md     # mỏng: OMI_CLI resume → làm tiếp theo step
  agents/
    omi-reviewer.md
    omi-security-reviewer.md
  hooks/
    hooks.json
    guard.py              # PreToolUse + SessionStart
  scripts/
    omi.py                # entrypoint mỏng → omi_hub.cli
    omi_hub/              # clean architecture, phụ thuộc chỉ đi vào trong
      config/             # workflow.json, templates.json, pr_template.json + hàm nạp
      domain/             # thuần: errors, lifecycle, rework, relations, guards, audit, planning, progress, render, templates, acceptance, security, text
      infrastructure/     # github/: subprocess gh api graphql / REST
      application/        # use case theo nhóm lệnh
      cli/                # argparse + in output
  templates/
    AGENTS.md
    ISSUE_TEMPLATE/config.yml   # forms <type>.yml do init sinh từ templates.json
    workflows/omi-audit.yml
  tests/
    test_domain_*.py, test_application_*.py, test_infrastructure_github.py, test_guard.py, test_doctor.py, test_feedback.py, test_cli_main.py, test_handoff.py, test_release.py
    e2e.sh
  docs/
```

Ranh giới:

- `domain/` không I/O, không import layer khác ngoài `domain`. Đầu vào: loại, status hiện tại, status đích, snapshot ngữ cảnh (parent, children, PR, blockers). Đầu ra: hợp lệ hay danh sách lỗi. Test được hoàn toàn bằng unittest.
- `config/` chỉ đọc file khai báo đi kèm plugin.
- `infrastructure/github/` là nơi duy nhất gọi `gh` (`client` → `issues`, `project`, `milestones`, `bootstrap`). Trả về dict thuần.
- `application/` ghép: đọc snapshot qua `infrastructure` → hỏi `domain` → ghi qua `infrastructure` → rollup. `cli/` chỉ parse tham số và in kết quả.
- Skills chỉ hướng dẫn Claude khi nào gọi lệnh nào; không chứa logic rule.

### 5.2 `workflow.json` (rút gọn)

```json
{
  "max_rework": 3,
  "statuses": ["Draft","Triage","Approved","Waiting","Ready","In Progress","In Review","In QA","Blocked","Done","Cancelled"],
  "terminal": ["Done","Cancelled"],
  "human_approval": ["Approved"],
  "types": {
    "Task": {
      "initial": "Draft",
      "parents": ["User Story","Functional Requirement","Non-Functional Requirement","Change Request"],
      "requires": ["parent"],
      "transitions": [
        {"from": "Draft", "to": "Ready", "guards": ["parent_ready", "no_open_blockers"]},
        {"from": "Draft", "to": "Waiting", "guards": ["parent_ready", "has_open_blockers"]},
        {"from": "Ready", "to": "Waiting", "guards": ["has_open_blockers"]},
        {"from": "Waiting", "to": "Ready", "guards": ["no_open_blockers"]},
        {"from": "Ready", "to": "In Progress", "guards": ["no_open_blockers"]},
        {"from": "In Progress", "to": "In Review", "guards": ["pr_open"]},
        {"from": "In Review", "to": "In QA"},
        {"from": "In QA", "to": "Done", "guards": ["pr_merged"]},
        {"from": ["Draft","Waiting","Ready","In Progress"], "to": "Cancelled", "guards": ["reason"]}
      ]
    }
  }
}
```

Blocked và rework là quy tắc chung, được `domain/` xử lý, không lặp trong từng loại. v1 dùng workflow.json đi kèm plugin; override theo repo để sau (YAGNI).

### 5.3 Lệnh CLI (`OMI_CLI` = `python "<plugin>/scripts/omi.py"`, đường dẫn đầy đủ do hook SessionStart in ra)

| Lệnh | Việc |
|---|---|
| `init --repo-dir R [--milestone M] [--test-cmd C] [--lint-cmd C] [--accept-cmd C] [--from-template N] [--template-only]` | Bootstrap (mục 6.1), idempotent; chạy lại sau khi cập nhật plugin (thêm option Status mới, giữ Status của item) |
| `doctor` | Kiểm workspace sau khi cập nhật plugin: version, `.github/`, settings, config, field/option Status, `OMI_CONFIG`, secret, default branch, ruleset; mỗi mục OK/WARN/FAIL; trước đó gửi lại hàng đợi feedback |
| `handoff` / `handoff note "<text>"` | Ghi lại mục tự động giữa `<!-- omi:handoff:auto -->` và `<!-- /omi:handoff:auto -->` trong `.omi/HANDOFF.md` (plugin, doctor rút gọn, task đang làm, Ready kế tiếp, Done từ lần trước, Draft/Triage, findings mở của Epic, hàng đợi feedback), giữ phần ngoài marker; xoá ghi chú phiên mà mọi `#n` đã đóng hoặc không có `#n` và cũ hơn 14 ngày. `note`: thêm `- YYYY-MM-DD: text` vào `## Ghi chú phiên`. `note --wip`: ghi đè dòng `Ý định` trong checkpoint wip. Lỗi GitHub → `HANDOFF WARN`, không đổi file |
| `feedback "<tiêu đề>" [--body] [--kind bug\|improve] [--cmd]` | Agent ghi bug/improvement của plugin thành issue ở repo plugin (`repository` trong `plugin.json`), label `omi-feedback`, body có project nguồn, version, lệnh liên quan; trùng title đang mở → comment +1; lỗi gửi → `.omi/feedback-queue.jsonl`, `FEEDBACK QUEUED`, gửi lại ở lần `feedback`/`doctor` sau |
| `release [--merge]` | Mở (hoặc dùng lại) PR develop→main liệt kê commit, request review team `org-owners`, bật auto-merge (merge commit) nếu được; không có commit mới → `NOTHING`. Mỗi lần chạy đồng bộ team = org owner. `--merge`: có owner org kết luận mới nhất APPROVED và không owner nào CHANGES_REQUESTED thì merge commit (`RELEASED`), không thì `RELEASE WAIT` |
| `new <type> "title" [--parent N] [--affects N,...] [--milestone M] [--priority P] [--estimate E] [--body-file F] [--field "Mục=nội dung"]... [--blocked-by N]...` | Tạo item, set type, parent, milestone kế thừa, thêm vào Project, set Status khởi tạo. Đã có issue mở cùng type + title → bổ sung phần thiếu (parent, Project, Status), in số cũ, không tạo trùng. `--blocked-by` (lặp lại) gắn quan hệ; khi duyệt Task còn blocker mở vào Waiting |
| `edit N --field "Mục=nội dung"... [--cr C]` | Thay mục body theo heading (mục phải có trong template của type, kiểm template trước khi ghi); `--cr` → comment changelog trỏ Change Request C |
| `move N <status> [--reason R]` | Kiểm tra + chuyển + đồng bộ open/closed + rollup; `Ready` khi còn blocked-by mở → `Waiting`; item kết thúc → item Waiting hết blocker về `Ready` |
| `rework N --reason R` | Mục 4.5 |
| `block N (--reason R \| --by M)` / `unblock N` | Mục 4.3 Blocked; chỉ `--by` (Task/Bug ở Draft/Triage/Ready) → Waiting; `unblock` về Waiting nếu còn blocker mở |
| `tree [N]` | In cây item kèm status, `⛔ #n` cho blocked-by đang mở |
| `next` | Task/Bug Ready, ưu tiên cao nhất, milestone sớm nhất, không bị chặn |
| `apply PLAN.json [--approve]` | Tạo cây từ plan, idempotent theo `omi:key`; tạo quan hệ `blocked_by` còn thiếu, Task Ready còn blocker mở → Waiting |
| `plan-show PLAN.json` | Validate (quan hệ + template + `blocked_by`, vòng lặp) + in cây plan (key, type, title, số AC, `⛔` phụ thuộc) |
| `template <type>` | In khung title + body chuẩn của loại (mục 3.6) |
| `pr-lint N` | Kiểm title + body PR theo template PR (mục 3.7); in `PR OK` hoặc `PR FAIL` + lỗi; PR release (head = develop) bỏ qua |
| `audit [--fix]` | Kiểm tra bất biến (mục 6.5); `--fix` thêm item thiếu vào Project / item chưa có Status với Status khởi tạo của type. `move` từ chưa có Status chỉ về status khởi tạo |
| `context N` | In ngữ cảnh gọn cho LLM: issue, AC của parent, item Affects, quy ước test AC, và đúng các mục docs được tham chiếu trong `### Tham chiếu` của issue/parent (`docs/x.md#anchor`, cắt tới heading cùng cấp; thiếu file/mục hoặc ngoài repo → cảnh báo), và `## Findings mang theo`: finding còn mở của parent + tổ tiên, mã `<p>.<i>` |
| `start [N]` | Chọn `next` nếu không có N; Draft→Ready→In Progress (còn blocked-by mở thì dừng ở Waiting, báo lỗi); checkout branch của issue |
| `check` | Chạy lần lượt `commands.lint`, `typecheck`, `scan`, `test` (cái nào cấu hình); in `CHECK PASS`, `CHECK WARN: chưa cấu hình commands.test` (exit 0, không có test) hoặc `CHECK FAIL (<bước>)` + 60 dòng cuối |
| `submit N [--findings p.i,...]` | `--findings`: kiểm mọi mã thuộc finding còn mở của parent/tổ tiên (sai → lỗi, không sửa gì) rồi đánh dấu `[x] ... (xong ở #N)`. Push, tạo PR (`Closes #N`) nếu chưa có, → In Review. Chưa có marker review: ghi gói review `.omi/tmp/review-N.md` (context, commit của nhánh, kết quả `check` gần nhất, Task anh em còn mở, findings đã có, diff đã bỏ lockfile/file sinh và ghi tên file bỏ), in `REVIEW ... reviewers=code[,security]`. Đã có marker: in `REVIEW ... reviewers=none` |
| `carry N...` | Task Draft (gợi ý review kiểu cũ) → finding của parent (title + `### Việc cần làm`, bỏ trùng), Task → Cancelled kèm lý do |
| `review-done N [--fail R \| --override R] [--improve T]...` | Ghi marker `<!-- omi:reviewed -->` **sau khi** reviewer trả kết quả; `--fail` → rework với lý do R; `--override` (chỉ sau khi người dùng xác nhận BLOCKER sai) → PASS, ghi lý do lên issue và PR, không rework; `--improve` (lặp lại được) → thêm `- [ ] T (từ #N)` vào comment `<!-- omi:findings -->` của parent (bỏ trùng, không tạo issue) |
| `status [--milestone M]` | Một truy vấn: tỉ lệ Done (item, Task/Bug), theo Epic, đếm theo Status, đang làm, Blocked + lý do, Waiting + issue đang chặn, rework, `Findings:` (finding còn mở của Epic đã Done), task kế tiếp |
| `resume` | Task dở trong `.omi/tmp/current` + Status + git (dirty, commit chưa merge) + marker review + gói review → `RESUME #n step=<code\|submit\|review\|qa\|blocked\|start\|next>` + gợi ý (+ context) |
| `qa N` | → In QA, chờ `gh pr checks --watch` (PR không có CI thì chạy `commands.test`, có CI thì không chạy trùng); fail → rework + log `.omi/tmp/qa-N.log`; pass → merge squash → Done → rollup → `accept` parent nếu parent vào In QA. Item sang In QA/Done còn finding mở → chuyển lên comment findings của parent (`chuyển từ #x`, dòng gốc `[x] ... (chuyển lên #p)`); item gốc kết thúc còn finding → in `FINDINGS OPEN #<n> <k>` |
| `accept N` | Nghiệm thu Story/Functional Requirement/Non-Functional Requirement: chạy `commands.accept` (thay `{n}`), mỗi AC tự động phải có test `ac<N>_<i>` pass, AC `[manual]` phải được tick; pass → Done; AC tự động fail → rework |
| `impact N [--post]` | Liệt kê item Affects của Change Request + item con kèm status; `--post` đăng comment có `<!-- omi:impact -->` |

Lỗi: in thông điệp rõ ràng (vì sao không hợp lệ, cần làm gì), exit code ≠ 0. Không có lệnh ghi một phần mà không báo.

### 5.4 Cấu hình: workspace và repo (D12)

```
<workspace>/                 # Claude Code mở ở đây
  AGENTS.md                  # hướng dẫn agent (init merge mục omi)
  .claude/                   # settings, agent-memory của reviewer
  .omi/project.json          # cấu hình omi
  .omi/plans/, .omi/tmp/     # plan từ PRD; gói review, log QA, current
  <repo_dir>/                # repo git — chỉ code, docs, .github/
    .github/ISSUE_TEMPLATE/*.yml, pull_request_template.md, workflows/omi-audit.yml
```

CLI tìm `.omi/project.json` từ cwd đi lên (chạy được ở workspace hoặc trong repo); mọi lệnh git/gh cần working copy và `commands.*` chạy với `cwd = <workspace>/<repo_dir>`. Trong GitHub Action không có workspace: `init` lưu config vào repo variable `OMI_CONFIG`, CLI đọc biến này khi không tìm thấy file.

**Workspace** — `.omi/project.json`: owner, repo, `repo_dir`, `default_branch` (develop), `main_branch`, project number, project node id, field id và option id (cache để khỏi tra mỗi lần), và:
  - `commands`: `{"lint": "...", "typecheck": "...", "scan": "gitleaks detect --no-banner && semgrep --error -q", "test": "...", "accept": "pytest -k ac{n}_ -rA"}` (lệnh shell của dự án, cái nào bỏ trống thì bỏ qua; `{n}` = số issue nghiệm thu).
  - `security_paths`: danh sách regex đường dẫn file kích hoạt security review (mặc định: auth, login, password, secret, token, crypto, permission, acl, session, `\.env`, sql).
  - `ci_infra_patterns`: danh sách regex log CI coi là lỗi hạ tầng (mặc định: `Input required and not supplied`, `Bad credentials`, `Resource not accessible by integration`, HTTP 5xx). Khớp → `qa` in `QA INFRA <đoạn khớp>`, không rework, giữ status.
  - `review_max_diff_lines`: cắt diff trong gói review (mặc định 1500).
- `.omi/tmp/`: gói review, log QA, `current` (task đang làm). Task Done/Cancelled → xoá `review-N.md`, `qa-N.log`; `start` xoá file cũ hơn 7 ngày (trừ `current` và file của task đang làm). `resume` dựa vào marker review trên GitHub nên vẫn đúng khi gói đã bị dọn.
- `.omi/plans/*.json`: các plan đã sinh từ PRD (giữ làm lịch sử).
- `AGENTS.md`: quy trình làm việc cho agent (từ template), có mục omi tóm tắt lifecycle và lệnh.

**Repo** (chỉ những gì GitHub bắt buộc nằm trong repo):

- `.github/ISSUE_TEMPLATE/*.yml`: issue forms, mỗi form có `type:` tương ứng.
- `.github/pull_request_template.md`.
- `.github/workflows/omi-audit.yml`.

### 5.5 Hooks

- **PreToolUse (Bash|PowerShell)**:
  - Chặn (`deny`) `gh issue close|reopen`, `gh project item-edit`, `gh api` có mutation `updateProjectV2ItemFieldValue` khi không đi qua `omi` → thông báo "dùng `omi move`".
  - `ask` khi lệnh là `omi move N Approved` (D7).
  - `ask` kèm gợi ý lệnh OMI_CLI khi gọi `gh issue create|edit|delete|transfer`, `gh issue comment --edit-last`, `gh project item-add|item-delete|item-archive|field-*`, mutation `addProjectV2ItemById`/`deleteProjectV2Item`/`addSubIssue`/`addBlockedBy` (repo cài plugin chỉ thao tác issue/Project qua OMI_CLI).
  - Chỉ so mẫu trên phần lệnh: bỏ nội dung heredoc (`<<EOF`), here-string PowerShell (`@'...'@`) và giá trị `--body`/`-b`.
- **PostToolUse (Bash|PowerShell|Edit|Write)**: chỉ khi có `.omi/tmp/current`; chạy song song git cục bộ (nhánh, status, commit cuối, shortstat), đọc `check-last.txt`, không gọi mạng (< 200 ms) → ghi mục `<!-- omi:handoff:wip -->` của `.omi/HANDOFF.md` (task, nhánh, bước, commit cuối, file chưa commit, check gần nhất, lệnh cuối, giữ dòng `Ý định` do `handoff note --wip` ghi). `resume` in mục này; task Done/Cancelled (hết `current`) → `handoff`/`resume` xoá mục.
- **SessionEnd**: workspace đã init → chạy `OMI_CLI handoff` (timeout 50 s, lỗi bỏ qua, không gọi LLM) để phiên dừng giữa task vẫn có HANDOFF mới. `qa` ra `DONE` và `move ... Cancelled` cũng tự chạy `handoff` (lỗi → `HANDOFF WARN`).
- **SessionStart**: in dòng `OMI_CLI: python "<CLAUDE_PLUGIN_ROOT>/scripts/omi.py"` để skills dùng đường dẫn tuyệt đối; nếu repo có `.omi/project.json` thì nhắc `next`/`tree`, nếu chưa thì gợi ý `OMI_CLI init` — trên 1 dòng; repo đã init in thêm dòng `QUY TẮC:` (issue/Project chỉ qua OMI_CLI; thiếu lệnh/plugin chạy sai → `OMI_CLI feedback`). Repo đã init và source là `startup`/`clear`: in thêm context task dở (`.omi/tmp/current`) hoặc `NEXT` (mục 6.3).

### 5.6 Subagents

Không có subagent viết code (D11).

- `omi-reviewer` (`memory: project`): chỉ đọc gói `.omi/tmp/review-N.md` (AC + diff); không khám phá repo trừ khi cần xác minh một dòng cụ thể. Checklist: sai so với yêu cầu/AC, lỗi logic, thiếu test cho hành vi chính, vượt phạm vi. Bỏ qua phong cách và mọi thứ lint/typecheck/test đã kiểm. Output: `VERDICT: PASS|FAIL`, tối đa 10 dòng `BLOCKER: file:line ...`, tùy chọn `IMPROVE: ...` (không ảnh hưởng verdict).
- `omi-security-reviewer` (`memory: project`): như reviewer, checklist injection, authn/authz, secret, crypto, input validation, lộ dữ liệu; mỗi blocker phải chỉ ra dòng cụ thể và cách khai thác. Chỉ được gọi khi `submit` in `security` trong `reviewers`.
- Phát hiện "chạm security" là việc của script: issue hoặc parent có label `security`; parent là Non-Functional Requirement nhóm Security; hoặc file trong PR khớp `security_paths`.

## 6. Luồng nghiệp vụ

### 6.1 Bootstrap (`OMI_CLI init`, người chạy trong terminal — không cần LLM)

Chạy từ thư mục workspace: `OMI_CLI init --repo-dir <repo>`. Tham số thêm: `--test-cmd`, `--lint-cmd`, `--accept-cmd` ghi vào `commands`.

1. Kiểm tra: `gh auth` có scope `project, repo, admin:org`; repo (trong `--repo-dir`) thuộc org.
2. Tạo Issue Types còn thiếu (REST `/orgs/{org}/issue-types`).
3. Tạo Project mới (hoặc `gh project copy` từ Project mẫu khi có `--from-template`; copy không mang workflow `Auto-add to project`) và tạo 5 view mục 3.4 bằng API (`createProjectV2View` + filter; group by/sort phải chỉnh tay), xoá view "View 1" GitHub tự tạo (`deleteProjectV2View`). Nếu đã có Project gắn repo với tiêu đề chuẩn → dùng lại.
4. Link Project với repo; đảm bảo field Priority/Estimate/Rework Count/Blocked Reason và đủ option Status (tạo bù nếu thiếu).
5. Built-in workflows: không có API. Plugin tự thêm item vào Project (`add_to_project`), không phụ thuộc Auto-add; `init` in hướng dẫn bật Auto-add trên UI nếu muốn. Item closed → không đổi (plugin tự quản Done/Cancelled).
6. Workspace: ghi `.omi/project.json`, `AGENTS.md` (merge mục omi nếu file đã có). Repo: issue forms, PR template, workflow audit. Repo variable `OMI_CONFIG` = config (cho Action). Label `security`.
7. Luồng release (D13): team `org-owners` = owner của org (tạo nếu chưa có, thêm/bớt thành viên cho khớp, quyền push repo); CODEOWNERS `* @<org>/org-owners` lên nhánh chính (contents API, trước ruleset), tạo develop từ nhánh chính, default branch = develop (bật merge commit + auto-merge), ruleset `omi-release` trên nhánh chính (cấm xóa/force push; PR + 1 approve + code owner, chỉ merge commit, approve cũ mất khi có push mới). Ruleset lỗi → cảnh báo, không dừng. CODEOWNERS khác nội dung khi ruleset đã chặn nhánh chính (repo cũ) → ghi lên develop, lên nhánh chính ở release kế tiếp. Nhánh chính: `main_branch` trong config, không có thì default branch hiện tại, default đã là develop thì nhánh `main`/`master` đang tồn tại. Config: `default_branch`=develop, `main_branch`.
8. Tùy chọn tạo milestone đầu.
9. In checklist việc người phải làm: tạo secret `OMI_PROJECT_TOKEN`; `git switch develop` rồi commit `.github/`.

Project mẫu (tùy chọn) tạo bằng `omi init --template-only` (fields + 5 view; group by/sort chỉnh tay).

### 6.2 PRD → cây item (`/omi-plan <prd>`)

1. Claude đọc PRD, sinh `.omi/plans/<date>-<slug>.json`: cây node `{key, type, title, body, priority, estimate, affects, children}`; node gốc có thể có `milestone` hoặc `parent` (số issue có sẵn); Task có thể có `blocked_by` (key hoặc số issue). Story/Functional Requirement/Non-Functional Requirement có acceptance criteria.
2. `domain/planning` kiểm tra quan hệ cha–con của plan trước khi trình.
3. `plan-show` in cây (script, không để LLM tự vẽ); người duyệt; sửa theo phản hồi.
4. `omi apply plan.json --approve`: tạo theo thứ tự cha trước con; bỏ qua node đã có `omi:key`; requirement items vào `Approved` (người đã duyệt plan = chốt baseline), Task vào `Ready`; sau đó tạo quan hệ blocked-by, Task còn blocker mở → `Waiting`.

### 6.3 Vòng implement (`/omi-implement [N]`)

Một agent (phiên chính) làm trọn task:

1. `start [N]` → `START #N` (hoặc `NONE` → dừng). `context N` → đọc yêu cầu + AC.
2. Viết code + test theo TDD (test AC tên `ac<parent>_<i>`), lặp `check` tới `CHECK PASS`, commit.
3. `submit N` → `REVIEW #N PR #P pack=<file> reviewers=code[,security]`.
4. Gọi `omi-reviewer` (và `omi-security-reviewer` nếu có) **song song, 1 lượt**; xong thì `review-done N` (PASS) hoặc `review-done N --fail "..."` (script rework).
   - `IMPROVE:` → `new Task "<gợi ý>" --parent <parent của N>` (Draft), không sửa trong task này.
   - Có `BLOCKER` → `review-done N --fail "<blocker gộp>"` (ghi nhận + rework) → tự sửa (cùng ngữ cảnh) → `check` → `submit N` (lần này `reviewers=none`, không review lại).
5. `qa N` →
   - `QA FAIL #N log=<file>` → script đã rework; đọc log, sửa, `check`, `submit N`, `qa N`.
   - `QA INFRA <lý do>` → lỗi hạ tầng CI (secret/input/GitHub 5xx), không rework: báo người dùng sửa cấu hình hoặc chạy lại `qa N`.
   - `DONE #N` → kèm các dòng rollup và `ACCEPT PASS|FAIL #p` nếu parent vào In QA.
6. Báo 1 dòng. Người dùng muốn làm tiếp: gõ `/clear` rồi `tiếp`.

**Tiếp tục công việc dở** (phiên bị tạm dừng, chạm limit 5h...): mở phiên mới → hook SessionStart chạy `resume` → dòng `RESUME #n step=...` + context có sẵn → người dùng gõ "tiếp" (skill `omi-resume`). Marker review chỉ ghi sau khi có kết quả (`review-done`), nên phiên chết giữa lúc review vẫn resume đúng về bước review.

**Xem tiến độ**: `! <OMI_CLI> status` (0 token) hoặc skill `omi-status`.

**Tự nạp ngữ cảnh sau `/clear`**: model không tự gọi được `/clear` (lệnh giao diện), nên người dùng gõ. Phần còn lại tự động: `start` ghi số task vào `.omi/tmp/current` (`qa` xóa khi Done); hook SessionStart (source `startup`/`clear`) chạy script: có task dở → in kết quả `resume` (bước tiếp + context); không có → in `NEXT: ...`. LLM không tốn lượt nào để dựng lại ngữ cảnh.

Nghiệm thu thất bại: `accept` đã rework parent; phiên chính tạo Task bổ sung `new Task "Đạt AC<i> của #p" --parent p` rồi chạy vòng trên. Thiếu tick AC `[manual]` → báo người, không làm gì thêm.

Bị Blocked (vượt rework) → dừng, báo người.

### 6.4 Change Request và Bug

- **Change Request**: `omi new "Change Request" "..." --parent <Epic> --affects 12,15` → Triage. `impact N --post` (script) đăng danh sách item bị ảnh hưởng kèm marker `<!-- omi:impact -->`; Claude chỉ đề xuất Task thêm/hủy dựa trên danh sách đó. Người duyệt → Approved. Claude tạo Task dưới Change Request. Task chạy vòng 6.3. Change Request tự Done khi Task xong; khi đó plugin comment changelog ("Thay đổi theo Change Request #x đã hoàn tất") lên từng item Affects (comment thay vì sửa body để không ghi đè nội dung người viết).
- **Bug**: `omi new Bug "..." --affects 42 --milestone M` → Triage. Bước tái hiện rõ ràng → Ready; không phải lỗi/trùng → Cancelled + lý do. Sau đó chạy vòng 6.3; bước đầu là viết test tái hiện (fail) rồi mới sửa (TDD), không tốn thêm lượt LLM riêng cho triage.

### 6.5 Audit (GitHub Action)

Trigger: `issues` (opened, edited, closed, reopened, typed, untyped, milestoned, demilestoned), `pull_request` (closed), cron hằng ngày, `workflow_dispatch`. Checkout repo omi-hub vào `.omi-hub/` rồi chạy `python .omi-hub/scripts/omi.py audit --fix` với `OMI_PROJECT_TOKEN` và `OMI_CONFIG: ${{ vars.OMI_CONFIG }}` (repo không có `.omi/` — D12).

Action không biết status trước đó (Projects không phát event cho Actions), nên kiểm tra **bất biến của trạng thái hiện tại**:

| Bất biến | Tự sửa? |
|---|---|
| Issue có type thuộc 7 loại | Không, báo |
| Status thuộc tập hợp lệ của loại | Không, báo |
| Parent đúng loại cho phép; item bắt buộc có parent thì có parent | Không, báo |
| Issue closed ⇔ Status Done/Cancelled | Có: closed+open-status → Done/Cancelled theo state_reason; Done/Cancelled+open → đóng |
| Story/Functional Requirement/Non-Functional Requirement/Epic Done ⇒ mọi con kết thúc | Không, báo |
| Blocked ⇒ có reason hoặc blocker mở | Không, báo |
| Waiting ⇒ còn blocker mở | Có: → Ready |
| Task/Bug Ready ⇒ không còn blocker mở (blocked-by thêm tay trên GitHub) | Có: → Waiting |
| Milestone con = milestone Epic tổ tiên | Có |
| Item trong repo chưa vào Project | Có: thêm, set Status khởi tạo |

Kết quả ghi vào một issue duy nhất "OMI Audit" (tạo nếu chưa có, cập nhật body, đóng khi sạch).

## 7. Xử lý lỗi

- `gh` lỗi (auth, scope, rate limit, GraphQL errors) → bọc trong `GhError` với thông điệp gốc + gợi ý (ví dụ thiếu scope → `gh auth refresh -s project`).
- Lệnh nhiều bước (`new`, `apply`, `init`) idempotent: chạy lại an toàn, tiếp tục từ chỗ dừng.
- `move` kiểm tra rule **trước** khi ghi; nếu ghi Status thành công nhưng rollup lỗi → báo rõ, `audit` phát hiện được.
- Không bao giờ xóa issue; hủy = Cancelled.

## 8. Kiểm thử

- `tests/test_domain_*.py` (unittest stdlib): mọi transition hợp lệ/không hợp lệ theo từng loại, Blocked/unblock, rework + phanh, quan hệ cha–con, rollup, guard.
- `tests/e2e.sh` (thủ công, sau mỗi phase): chạy trên repo sandbox của org: init → apply plan mẫu → vòng implement một Task giả → audit sạch.

## 9. Rủi ro và điểm cần spike (Phase 0)

| Điểm | Phương án nếu không đạt |
|---|---|
| REST tạo issue type cho org và gán type cho issue | Không có phương án thay; điều kiện tiên quyết |
| Sub-issues API (`addSubIssue`, đọc children) | Điều kiện tiên quyết |
| ✓ Issue dependencies API (REST `dependencies/blocked_by`, GraphQL `blockedBy`/`blocking`) | — |
| `gh project copy` giữ views + built-in workflows | Views: giữ ✓, thiếu thì tạo bằng REST `projectsV2/{n}/views`. Workflow Auto-add: không giữ → plugin tự thêm item |
| Projects có cột Type cho issue types — ✗ `field-list` và GraphQL `fields` không trả field Type (spike mục 6) | Không dùng field Type trong Project: type lấy từ `issueType` của issue (snapshot, audit, tree) |
| ✓ 2026-11-24: tạo Issue Type tên dài; issue với `type` (REST); `POST sub_issues`; `updateProjectV2Field` options Status | — |
| Gắn sub-issue cho item đã trong Project → GitHub **tự thêm** vào Project (bất đồng bộ), `addProjectV2ItemById` lỗi `Content already exists` (2026-11-24) | `add_to_project` bắt lỗi này, tìm lại item, thử lại |
| Action trigger `issues: typed` | Bỏ trigger đó, dựa vào cron |
| Issue forms hỗ trợ `type:` | Bỏ, plugin set type sau khi tạo (audit) |
| Subagent `memory: project` ghi vào `.claude/agent-memory/` | Ghi chú memory vào AGENTS.md |
| Issue Type tên dài có dấu cách (`Non-Functional Requirement`) | Rút gọn tên type nhưng giữ prefix title đầy đủ |
| Fine-grained PAT truy cập Project v2 của org | Dùng classic PAT scope `project, repo` |
| `updateProjectV2Field` thay options Status của Project rỗng | Sửa options Status bằng tay trong Project mẫu |
| `gh api --paginate --slurp` | Tự phân trang bằng `?page=` |
| Hook nhận `CLAUDE_PLUGIN_ROOT` | Skill dùng `${CLAUDE_PLUGIN_ROOT}` trực tiếp |
