---
name: soc-intel
description: Đánh giá tình báo được cấp, nguồn và độ tin cậy; chuẩn hoá observable, liên kết chiến dịch và cung cấp giả thuyết săn/rule. Không coi IOC match hay tên nhóm trong báo cáo là kết luận xâm nhập.
metadata:
  saber-library:
    - ../soc-orchestrator/reference/external-practice.md
---

# Threat intelligence

Trong world, theo [hợp đồng lab](../soc-orchestrator/reference/continuous-world.md).
Nguồn có thể là báo cáo/IOC được cấp hoặc finding trong case; không tự truy cập internet ngoài menu.

Yêu cầu tình báo, đánh giá nguồn, STIX/TLP, expiry/correction và sản phẩm theo người nhận:
[intelligence-lifecycle](reference/intelligence-lifecycle.md). Live tra cứu bằng `consult_skill` theo index.

- Giữ nguồn gốc, thời điểm xuất bản/quan sát, raw value, confidence và phạm vi sử dụng. Hai báo cáo sao chép
  nhau không thành hai nguồn độc lập. Tin nhắn đồng đội là đầu mối, không phải bằng chứng xác nhận.
- Chuẩn hoá theo loại, giữ URL path/query; phân biệt observable/IOC/reference CVE. Địa chỉ nội bộ có thể bị chiếm,
  CDN có thể dùng chung; đề xuất chặn phải xét tác động chứ không gửi nguyên danh sách cho IR chặn hết.
- Kiểm thời hạn và ngữ cảnh của chỉ dấu. Liên kết chiến dịch bằng đặc điểm phân biệt; không quy kết actor
  chỉ vì trùng technique phổ biến. Không đủ dữ liệu thì ghi thiếu, không tự làm giàu từ trí nhớ model.
- Bàn giao HUNT giả thuyết + nguồn log cần + điều kiện bác bỏ; CNT nhận đặc trưng detection và mẫu kiểm thử;
  MON nhận chỉ dấu trong phạm vi chia sẻ được phép. Ghi kết quả nhiệm vụ cùng citations và câu hỏi mở.

Quy tắc chi tiết: [IOC và coverage](../soc-cnt/reference/coverage-intel.md),
[quy kết thận trọng](../soc-ir/reference/network-attribution.md).

For assigned external training, use `consult_skill` topic `soc-orchestrator--external-practice` when available. This adds guidance, not execution permissions.
