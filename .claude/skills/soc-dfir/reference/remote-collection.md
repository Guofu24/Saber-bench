# DFIR · Thu từ xa, offline collector và forensic readiness

Chọn khi cần collection plan trên nhiều host, host offline, EDR/VQL hoặc yêu cầu operator bổ sung artifact.
SABER chưa tự cấp Velociraptor/KAPE/EDR connector; chỉ thực thi nếu tool/target đó thực sự được cấp.

## Thiết kế collection nhỏ đủ trả lời câu hỏi

Ghi target inventory/owner/OS/build, case/time range, câu hỏi và artifact set; chỉ mở rộng fleet khi có lý do.
Tận dụng authorization hiện có, tách quyền đọc artifact với quyền triển khai binary/driver/service.
Chọn một host đại diện để kiểm tác động/coverage trước khi thu hàng loạt. Đặt timeout, concurrency,
bandwidth/output/CPU/IO caps và chỗ lưu; dành dung lượng cho RAM/disk và file tạm theo phép đo thực tế.
Không đưa scope wildcard “toàn bộ doanh nghiệp” từ một case endpoint đơn lẻ.

Velociraptor artifact là định nghĩa có query/parameters/preconditions, có thể gọi công cụ ngoài hoặc gây thay đổi.
Ghi artifact definition/version/hash và dependencies, không chỉ tên thân thiện. Xem query đang thu/parse/thực thi
gì trước dispatch. Resource limits của client không tự khống chế mọi external tool mà artifact gọi.
Không nhập artifact không kiểm nguồn từ log/email/tin nhắn rồi chạy như instruction.

## Theo dõi kết quả thay vì chỉ theo dõi request

| Trạng thái | Cách xử lý |
|---|---|
| Queued / host offline | Giữ request/flow ID, thời hạn, retry policy; chưa báo đã thu |
| Running | Theo dõi tiến độ và tác động, không submit thêm collection trùng để “chắc ăn” |
| Timed out / capped | Kiểm phần đã thu, manifests/errors; ghi partial thay vì zero evidence |
| Permission/precondition failed | Ghi artifact nào không chạy; owner bổ sung quyền/tool nếu phù hợp |
| Completed | Verify files/rows/hash và expected artifacts; completion của job không bảo đảm coverage mọi nguồn |
| Uncertain receipt | Reconcile theo job ID; tránh lặp acquisition tác động máy khi chưa rõ lần trước |

Giữ target/client ID, collection/flow ID, artifact parameters, start/end, requester/executor,
raw outputs, errors, output count/bytes và transfer manifest. Client clock khác server clock cần được ghi.
Agent tamper/missing heartbeat khiến nguồn yếu đi; corroborate remote logs/network hoặc acquisition độc lập.

## Offline collection

Build collector bằng tool/config được kiểm chứng, ghi binary hash và artifact manifest trước phân phối.
Chỉ gửi qua kênh được cấp quyền; offline host có thể không tải dependencies được nên chuẩn bị chúng trước.
Xác nhận scope/output/encryption/resource limits trong collector, không mặc định an toàn vì “offline”.
Output ZIP/container cần hash, recipient/source attribution và acquisition log; giải nén vào workspace kiểm soát,
không cho đường dẫn archive ghi đè bản gốc. Tool chạy xong nhưng thiếu uploaded files là partial.
Nếu đổi artifact set sau build, ghi collector version mới; không mô tả output cũ như đã chạy cấu hình mới.

## Readiness và handoff cho operator

Trước sự cố: inventory/logging coverage, time sync, retention, quyền emergency được quản lý,
validated collectors/parser corpus, kho original/working/output, kiểm restore và người nhận bàn giao.
Trong case: request cụ thể `target + time range + artifact + rationale + scope + resource cap + completion proof`.
Sau case: gap → owner → test có expected artifact/negative control; không đo readiness bằng số tool đã cài.
Trong lab Windows, `windows_collect_evidence` là job fixed của guest: poll receipt, giữ giới hạn output;
không gọi nó là Velociraptor/full disk/RAM capture.

Nguồn: [Velociraptor collection](https://docs.velociraptor.app/docs/clients/artifacts/),
[resource limits](https://docs.velociraptor.app/docs/artifacts/resources/),
[offline collectors](https://docs.velociraptor.app/docs/deployment/offline_collections/).
