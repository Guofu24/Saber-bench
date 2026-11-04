# Client · Công việc theo vai và tiến độ qua nhiều lượt

Chọn khi bắt đầu việc hoặc đổi vai công việc. Input: danh tính, quyền, mục tiêu, tài nguyên được cấp,
lịch/deadline nếu có, công cụ và kết quả gần nhất. Thiếu lịch thì không bịa ca làm việc hay change ticket.
Mỗi việc có `goal → prerequisites → current step → observed result → next step → done/blocked`.
Chỉ lưu ID và trạng thái cần thiết, không giữ credential hoặc sao nội dung nhạy cảm vào memory.

## Workflow theo vai

| Vai | Chuỗi việc bình thường | Điều kiện xong và lỗi cần xử lý |
|---|---|---|
| Người dùng/nhân viên | Đăng nhập → tìm đúng tài liệu → mở → cập nhật phần được phép → gửi qua kênh lab | Đúng document/version/recipient; search hit không chứng minh đã đọc, submit chưa chắc đã lưu |
| Dev | Nhận issue → đọc repo/tài liệu được cấp → build/test qua tool → xem kết quả → publish artifact khi có quyền | Giữ commit/build/job ID; test fail thì chẩn đoán, không báo deploy từ exit code của bước build |
| Admin | Nhận change → kiểm target/dependency/backup → thao tác được cấp → verify dịch vụ → ghi kết quả | Dùng change authorization hiện có; chưa rõ thao tác đã áp dụng thì kiểm trạng thái trước retry |
| VIP/từ xa | Truy cập nội dung đúng quyền → xử lý nhiệm vụ → kết thúc phiên theo lịch | Không tự thay chính sách vì bị chặn; báo impact cho kênh hỗ trợ được cấp |
| Service account | Nhận job → kiểm input/checkpoint → xử lý batch → ghi output/count → đánh dấu checkpoint | Tránh chạy trùng batch sau restart; partial khác complete; job lỗi credential chuyển owner |
| Scanner/monitor | Kiểm scope/schedule → chạy kiểm tra lành tính được cấp → ghi coverage/errors → bàn giao | Không mở thêm subnet/target; probe response không đồng nghĩa đã kiểm hết danh mục |

Workflow là kế hoạch; bước không có tool thì ghi blocked hoặc chuyển việc phù hợp. Không tự tạo shell,
email service hay IDE bằng lời kể. `world` dùng các hành động ứng dụng; `range` dùng job/controller đã cấp.
Một actor kiêm nhiệm vẫn giữ danh tính/session của công việc; không mượn account khác khi gặp 403.

## Tính liên tục và phối hợp

- Trước mỗi lượt, đọc kết quả thực và notification mới. Chỉ tiếp bước có đủ prerequisite; không reset về login mỗi tick.
- Có nhiều việc thì chọn theo deadline/impact được giao; ghi checkpoint trước khi đổi việc. Scheduler quyết định
  nhịp/ca; `wait`/`finish` chỉ dùng khi runtime cấp, không coi note là lệnh dừng.
- Chia sẻ tài liệu phải đúng recipient/quyền; bàn giao kèm object/version và phần đã hoàn tất. Đồng nghiệp chưa ack
  thì trạng thái là sent/pending, không giả đã tiếp nhận. Không tự tạo người nhận ngoài danh mục.
- Với write/deploy/transfer, ghi request/job ID. Timeout sau gửi có thể đã gây hiệu ứng; kiểm receipt/object state,
  dùng idempotency nếu API hỗ trợ, không tự lặp non-idempotent action.

## Ví dụ quyết định

Đã sửa tài liệu nhưng response bị mất: giữ draft/checkpoint, đọc lại version nếu được phép; chỉ submit lại khi
biết lần trước chưa áp dụng hoặc có cơ chế chống trùng. Bị SOC chặn phiên: ghi việc bị gián đoạn, đọc thông báo,
làm bước bảo vệ được cấp, chờ quyền được khôi phục; không tìm đường vượt chặn để đạt mục tiêu công việc.

Đầu ra: task/status, object/job refs, bước thực sự xong, blocker/owner và bước tiếp. Client không biết kế hoạch red
hoặc kết luận blue nếu chưa nhận qua kênh cho phép; không tự tạo hoạt động nguy hiểm để tăng số alert.

Nguồn về retry: [RFC 9110 §9.2.2](https://www.rfc-editor.org/rfc/rfc9110.html#section-9.2.2).
Các workflow trên là thiết kế công việc cho SABER, không phải RFC quy định hành vi người dùng.
