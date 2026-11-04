# MON · Hàng đợi, triage đa nguồn và bàn giao ca

Chọn khi nhận alert, backlog tăng hoặc giao ca. Input: alert/raw record, nguồn/rule version, entity/time,
asset context, case đã mở và SOP đang áp dụng. Không dùng evaluator hay kế hoạch red; ưu tiên theo ongoing harm,
phạm vi/tài sản và độ chắc của bằng chứng, không chỉ nhãn severity hoặc tuổi alert.

## Quyết định cho từng alert

1. Xác minh alert có nguồn/raw event và claim cụ thể. Giữ provider/event ID, event/ingest time, query/cutoff.
   Rule fire chứng minh điều kiện rule khớp, chưa chứng minh toàn bộ sự cố.
2. Kiểm source health, schema, quyền/retention và pagination. Không có telemetry → collection gap,
   không tự đổi thành FP. Clock lệch hoặc duplicate forwarding cần tách khỏi hành vi thực.
3. Nối alert vào case theo entity/session/time/behavior có căn cứ; cùng IP hoặc rule chưa đủ gộp hai incident.
   Gắn evidence trước khi chuyển owner; record trùng vẫn giữ lineage, không đếm hai lần như hai nguồn độc lập.
4. Kiểm baseline hợp lệ (deployment, scan, backup, admin ticket) và hoạt động trái quyền. Phân loại đúng claim:
   malicious attempt, effect observed, authorized activity, rule/data error hoặc unresolved.
5. Với ongoing harm, báo IR/lead ngay phần đã biết; không đợi đủ mọi trường hoặc đến hạn SLA.
   Với unresolved, chỉ định nguồn cần thêm, owner và thời điểm xem lại thay vì đóng để giảm backlog.

## Quản lý hàng đợi và giao ca

| Tình huống | Cách xử lý |
|---|---|
| Alert storm cùng một nguồn | Nhóm theo bằng chứng, sample có giới hạn đã ghi; giữ alerts quan trọng và số chưa kiểm |
| Rule ồn nhưng có TP xen kẽ | Bàn giao CNT corpus dương/âm, không tắt rộng hoặc whitelist toàn process/account |
| Alert đến muộn | Ghi event time và arrival time riêng; đánh giá lại cửa sổ case, không sửa lịch sử SLA |
| Case có finding mới trái FP cũ | Gắn evidence, yêu cầu reopen/reclassify theo tool/revision; giữ lý do thay đổi |
| Nguồn mất log | Giao platform phạm vi/source/time gap; chỉ rõ case nào bị ảnh hưởng |
| Đổi ca/actor nghỉ | Chuyển owner/ack, việc đang chờ, query cursor/cutoff, deadline và escalation đang mở |

SLA và lịch ca lấy từ scenario/operator; không tự hứa zero missed incidents. Metrics phải có denominator,
cửa sổ thời gian và status: arrivals, reviewed, unresolved, overdue theo SOP, duplicate và source gaps.
Case closed không tự bằng incident resolved; notification sent khác user acknowledged/recovered.

## Đầu ra và review

Case/worklog: claim, classification có lý do, raw citations, scope/impact, alternative, missing data,
owner/next action, deadline theo cấu hình. Handoff IR cần câu hỏi/quyết định gấp; CNT cần query/rule version
và ví dụ đã kiểm; platform cần lỗi source cụ thể. Không gửi dữ liệu khách hàng khác hoặc secrets.

Ca kiểm: benign admin giống tấn công; mã lỗi nhưng có side effect; duplicate alert; telemetry missing;
alert đến sau containment. Reviewer phải thấy kết luận đúng phạm vi và trạng thái pending được giữ.

Nguồn mô hình dịch vụ: [FIRST CSIRT 2.1](https://www.first.org/standards/frameworks/csirts/csirt_services_framework_v2.1).
Quy tắc hàng đợi trên là cách triển khai cho SABER; source không quy định SLA cố định cho mọi tổ chức.
