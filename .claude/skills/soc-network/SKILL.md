---
name: soc-network
description: Điều tra luồng mạng, PCAP/DNS/HTTP/TLS và liên kết endpoint khi có nguồn tương ứng; kiểm C2, tunneling, NAT và bằng chứng exfil. Không suy lưu lượng packet từ telemetry ứng dụng.
---

# Điều tra mạng

Trong world, theo [hợp đồng lab](../soc-orchestrator/reference/continuous-world.md).
Nhận câu hỏi, điểm quan sát, thời gian chốt và dữ liệu flow/PCAP nếu có.

1. Kiểm nguồn/retention và packet loss, TLS, NAT, clock offset. Trong application lab chỉ có HTTP event nội bộ;
   không gọi đó là PCAP hay khẳng định đã thấy DNS/TLS nếu nguồn không được cấp.
2. Truy vấn hẹp theo principal/target/thời gian, phân trang; nối các phiên với endpoint/process bằng dữ liệu thật.
   Không loại RFC1918/cổng quen hoặc ép C2 có chu kỳ cố định.
3. Đánh giá attempt, liên lạc thành công và truyền dữ liệu riêng; ghi điểm quan sát/chiều/cách loại trùng khi tính bytes.
   Lượng traffic không tự bằng số byte dữ liệu nhạy cảm đã mất.
4. Ghi finding có ID phiên/event/offset, giả thuyết thay thế, phạm vi chưa thấy. Bàn giao IR điểm chặn hẹp cùng
   phụ thuộc dịch vụ; CNT nhận đặc trưng có thể phát hiện. Không tự chặn mạng khi không có quyền phản ứng.

Nguồn có PCAP: [C2/exfil](../soc-ir/reference/network-attribution.md).
Hồ sơ: [case record](../soc-orchestrator/reference/case-record.md).
