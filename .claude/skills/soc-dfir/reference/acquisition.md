# DFIR · Thu, bảo toàn và kiểm chất lượng chứng cứ

Dùng khi chọn artifact hoặc nhận gói thu. Đầu ra: collection plan, evidence register,
acquisition/QC result và custody; không chỉ một danh sách file.

## Chọn phương pháp theo câu hỏi

| Phương pháp | Câu hỏi phù hợp | Giới hạn phải ghi |
|---|---|---|
| Live triage | Process/session/socket đang tồn tại, log sắp xoay vòng | Thay đổi máy, quyền, timeout, EDR tamper, process ngắn bị bỏ sót |
| RAM/process memory | Injection, module/socket, trạng thái volatile liên quan case | Tương thích build/kernel, smear, crash risk, bí mật; disk snapshot không thay RAM |
| Logical files/export | Artifact chọn lọc, EVTX/journal/registry/app/cloud logs | Không bao phủ mọi sector, deleted/unallocated; quyền/filter giới hạn dữ liệu |
| Physical image | Filesystem/deleted data, metadata, examination cần sâu | Encryption, TRIM, bad sectors, thiết bị/định dạng; không hứa phục hồi mọi dữ liệu |
| VM/cloud snapshot | Giữ trạng thái volume/resource, clone để phân tích | Snapshot ID, consistency, attached volumes; không mặc định có RAM hoặc application consistency |
| Provider/third-party export | SaaS/control-plane hoặc nguồn không truy cập trực tiếp | Request/job ID, pagination, schema, nguồn xác nhận, thời điểm export khác event time |

Chốt scope và authorization đã có; ghi bổ sung nếu thay target, loại dữ liệu hay phương pháp ngoài phạm vi.
Ưu tiên nguồn dễ mất và có giá trị quyết định. Khi đang có tác hại, bàn giao IR lựa chọn cô lập trước/thu song song;
ghi tác động tới đường quản trị và evidence có thể mất. Khi case quy định SOP cố định, giữ điều kiện riêng đó.
Live thu read-only vẫn có thể đổi atime/log/cache hoặc gây tải; không cam kết “không thay đổi máy”.

## Evidence register và custody

Mỗi item giữ các trường có thật; dùng `unknown`/`not_available` kèm lý do thay vì tự tạo:

```text
case_id, evidence_id, source_host_or_tenant_resource_id, owner, authorized_scope_ref
source_type, acquisition_method, collector, start_utc, end_utc, source_clock_context
tool_version, sanitized_parameters_or_query_ref, original_format, byte_count
sha256_of_acquired_bytes, verification_time, immutable_location_or_storage_controls
errors, partial_or_truncated, source_time_range, coverage_gaps, classification
working_copy_ref, derived_from_evidence_id, retention_or_hold_ref
transfers: from, to, time, purpose, hash_verification, access_record
```

Hash bản export là hash bytes đã thu, không phải hash của toàn bộ dịch vụ hay bảo đảm tính thật của log.
Nguồn API/stream không có “source hash” ổn định: ghi manifest, request/source IDs, raw export hash và hạn chế.
Redacted/normalized/unpacked file là **derived evidence** có hash và lineage riêng; không ghi đè original.
Thiếu custody trước lúc tiếp nhận: ghi điểm bắt đầu biết được, người giao và khoảng trống; không bịa lịch sử.

## QC và xử lý lỗi

1. Đối chiếu target, time range, format, size và identity của collector. Giữ acquisition log/error.
2. Hash khi tiếp nhận/sao chép; verify working copy. Mismatch thì giữ cả bản nghi vấn và log,
   ngừng dùng bản không xác minh cho kết luận phụ thuộc integrity; lấy lại từ nguồn tin cậy nếu có.
3. Kiểm parser warnings, missing segments, read errors, bad sectors, rate limits, quyền và hết pagination.
   “File mở được” chưa chứng minh acquisition đầy đủ. Ghi partial cùng phạm vi còn dùng được.
4. Lưu original trong kho được cấp quyền; tách working copy và output. Quyền truy cập/retention theo case,
   không đưa image/token/PII vào chat, reputation service hoặc sandbox công cộng.
5. Handoff phải trỏ raw record cùng derived output; reviewer cần tái lập được method/version/query.
   Giữ item thiếu metadata với hạn chế; không tự phán quyết tính chấp nhận pháp lý.

Mất một nguồn không buộc ngừng mọi điều tra: dùng nguồn độc lập còn hợp lệ và thu hẹp assertion.
Không lặp lại acquisition tác động máy nếu lỗi chưa rõ nguyên nhân; ghi dependency cho operator.

Nguồn đối chiếu: [SWGDE Acquisition 2.1](https://www.swgde.org/documents/published-complete-listing/17-f-002-2-1/),
[SWGDE Collection 2.0, 20/11/2025](https://www.swgde.org/documents/published-complete-listing/18-f-002-2-0/).
