# Red · Thiết kế chiến dịch emulation có phạm vi và bằng chứng

Chọn khi nhận mục tiêu hoặc bàn giao chiến dịch. Input: campaign ID, targets/identities được cấp,
menu tool, thời gian/budget, exclusions, mục tiêu đo được và stop conditions. Dùng authorization của operator;
thiếu khả năng không tự mở thêm hạ tầng, target hay payload. Chỉ hoạt động trong lab đã cấp.

## Từ mục tiêu tới kế hoạch

1. Viết mục tiêu thành trạng thái quan sát được: truy cập object lab bằng principal không được phép,
   chuyển marker được cấp tới sink nội bộ, hoặc đo tác động ứng dụng bằng action mô phỏng có giới hạn.
   “Có HTTP 200” hay “đã gọi tool” không phải mục tiêu bảo mật.
2. Lập một nhánh tối thiểu: prerequisites → observation → hành động trong menu → expected effect → evidence.
   Dùng ATT&CK để mô tả hành vi nếu có căn cứ; không ép chiến dịch phải đi đủ mọi tactic.
3. Kiểm dependency: target tồn tại, quyền/foothold được scenario cấp hoặc đã xác minh, endpoint/sink trong scope,
   rate/budget còn, observer hoạt động. Không dùng kiến thức evaluator hoặc log riêng blue để chọn đường đi.
4. Chia recon/access/impact theo owner. Handoff phải có resource/principal, time, receipt, việc chưa thử.
   Actor nhận kiểm lại scope/prerequisite; một tin nhắn thành công không cấp quyền hay chứng minh foothold.
5. Với mỗi lần thử, ghi observed/blocked/failed/inconclusive cùng nguyên nhân. Chỉ đổi nhánh khi có dữ kiện mới;
   lỗi transport, tool unavailable và control chặn là các kết quả khác nhau.

## Phối hợp và dừng

- Tránh hai actor cùng tác động một target/job khi kết quả lần trước chưa rõ. Kênh red ghi claim và owner;
  việc không có lock/ack runtime phải ghi chưa bảo đảm thay vì giả coordination thành công.
- Nhịp do budget/scheduler/operator điều khiển. Không tự tăng lượng request để phá dịch vụ; mức gián đoạn chỉ
  dùng action cho phép và phạm vi kịch bản. Đạt mục tiêu, hết budget, target drift hoặc risk vượt scope thì dừng tác động.
- Red không đọc blue case nội bộ/ground truth. Không suy “không bị phát hiện” từ việc mình không thấy alert.
  Đánh giá detection/response thuộc evaluator/operator với telemetry riêng sau run.
- Khóa phiên bản plan/tool/scenario để tái lập. Thay đổi mục tiêu cần revision; không xóa attempts thất bại.

## Bản ghi chiến dịch

`objective / authorized scope / owner / step / prerequisites / tool+args ref / receipt / observed effect /
status / next branch / remaining budget / stop reason / artifacts needing cleanup`.
Không ghi secret value. Thành công/độ phủ chỉ áp dụng cấu hình lab và điểm quan sát đã kiểm, không suy ra production.

Nguồn thiết kế: [NIST SP 800-115](https://csrc.nist.gov/pubs/sp/800/115/final),
[MITRE adversary emulation plans](https://attack.mitre.org/resources/adversary-emulation-plans/).
Các ví dụ trong nguồn không tự trở thành tool hoặc quyền thực thi của agent.
