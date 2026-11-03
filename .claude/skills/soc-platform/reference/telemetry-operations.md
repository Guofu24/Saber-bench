# Platform · Sức khỏe telemetry, SIEM/SOAR và thay đổi có kiểm chứng

Chọn khi log gap, parser/query errors, delayed alerts, job backlog hoặc chuẩn bị nguồn mới.
Input: asset/source inventory, expected event types, schema/version, ingest path, retention/access,
service owners và baseline. Không coi danh sách tool đã cài là bằng chứng dữ liệu đang tới được analyst.

## Kiểm theo đường đi dữ liệu

`producer → agent/collector → transport/queue → parse/normalize → storage/index → query/rule → case/job`.
Mỗi chặng cần timestamp/identity/counter hoặc receipt phù hợp. Tách event/receive/ingest/query time;
clock skew, buffering và late arrival có thể gây khoảng trống giả. Kiểm quyền query trước khi báo mất dữ liệu.

| Quan sát | Kiểm tiếp |
|---|---|
| Không có events | Workload có phát sinh không, audit/filter có bật, sensor heartbeat và quyền đọc |
| Input có, output thiếu | Queue/retry/drop counters, rejected events, downstream timeout/capacity |
| Raw có, query không thấy | Index/tenant/time filter, parse errors, field mapping/types, retention/tiering |
| Query có, alert không có | Rule version/enabled state, source prerequisites/window và execution errors |
| SOAR accepted nhưng không hiệu lực | Job state, worker receipt, target/capability, retries và postcondition |
| Ingestion tăng sau restart | Backfill/duplicate IDs, checkpoint/cursor, ordering, không tự coi là attack spike |

Internal metrics phụ thuộc collector/version/config; tra đúng schema, không hardcode tên metric từ bản khác.
Queue/retry/WAL giúp chịu lỗi nhưng không bảo đảm không mất log: capacity, retry expiry và storage failure
vẫn có thể gây loss. Không thay offset/cursor hay replay toàn bộ pipeline khi chưa đánh giá duplicate/side effects.

## Sửa và onboard nguồn

Xác định lỗi tại chặng nào bằng mẫu raw và counters; giữ evidence trước thay đổi. Đề xuất target/config diff,
owner, resource/storage estimate, ảnh hưởng queries/rules, rollback và phép kiểm end-to-end.
Chỉ áp dụng qua tool/quyền hiện có. Có sample events tại nguồn → đúng fields/time/entity ở query → rule/case
nhận đúng là phép kiểm tốt hơn một health endpoint xanh; dùng benign canary do operator cấp.

Parser upgrade cần regression malformed/missing fields/locale/timezone và corpus cũ. Schema drift phải báo
CNT/HUNT/DFIR; không silently drop fields để đếm ingest thành công. Retention/archive/restore cần scope,
hash/lineage và quyền; không mở sealed archive hay tự xóa evidence để giải phóng đĩa.

Sau sửa, ghi thời điểm nguồn phục hồi, backlog đã xử lý, duplicate/drop còn lại và khoảng quá khứ không khôi
phục được. Bàn giao lead những case/hypotheses bị giảm confidence; không gọi history complete chỉ vì log mới tới.
SLO/capacity/retention lấy từ operator, không suy từ số agent hay số GiB mặc định của profile.

Ca kiểm: silent parser failure; clock lệch; queue đầy; source thực sự idle; query không có quyền;
SOAR job stuck. Đầu ra phải có chặng lỗi, evidence, impact, thay đổi/receipt và test sau sửa.

Nguồn: [OpenTelemetry internal telemetry](https://opentelemetry.io/docs/collector/internal-telemetry/),
[resiliency](https://opentelemetry.io/docs/collector/resiliency/),
[joint logging guidance](https://www.cyber.gov.au/publication/best-practices-for-event-logging-and-threat-detection).
