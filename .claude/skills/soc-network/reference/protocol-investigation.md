# Network · Điều tra theo điểm quan sát và protocol

Chọn cho câu hỏi liên lạc, C2, tunneling hoặc truyền dữ liệu. Input: sensor/interface/location, capture time,
flow/PCAP/raw logs, asset/NAT/proxy context và câu hỏi cần chứng minh. World HTTP receipts không tự thành PCAP.

## Kiểm dữ liệu trước pivot

Ghi capture filter/snaplen nếu có, dropped/missed packets, ingress/egress direction, asymmetric routing,
TLS visibility, clocks và retention. Kiểm sensor restart và log version. Bytes từ nhiều sensors có thể đếm trùng.
Giữ PCAP gốc, hash working copy và query/parser version; tệp trích từ stream là derivative có lineage.
Truncated capture, missing handshake hoặc encrypted payload cần giữ unknown thay vì suy đủ nội dung.

## Protocol và khóa nối

| Nguồn | Pivot có ích | Không được suy quá mức |
|---|---|---|
| Zeek conn | Sensor/time + uid, originator/responder, proto/service, conn_state, missed_bytes | UID phải có scope dataset/sensor; orig không luôn đồng nghĩa máy nội bộ/attacker |
| Suricata EVE | Sensor/time + flow_id; event_type/alert/protocol/file records | Alert không tự là block; kiểm action/config và effect. Community ID chỉ dùng khi có/config tương thích |
| DNS | Client/resolver/time, query/type/rcode/answer/TTL, cache/forwarding | Query khác resolution và connection; shared resolver không xác nhận endpoint nguồn |
| HTTP/proxy | Request/trace ID, method/host/path/status, principal/upstream khi có | Proxy status không luôn là backend status; URL path/query có semantics riêng, không lower toàn bộ |
| TLS/QUIC | Session/cert/server name khi thấy, endpoint/process/time | Fingerprint/cert reuse không chứng minh actor; encryption/ECH có thể hạn chế quan sát |
| PCAP/flow | 5-tuple + time/lifetime, retransmission/reassembly, directional bytes | Flow count/bytes không tự là số file/nội dung đã rời tổ chức |

Nối session với process/identity qua endpoint/proxy/NAT records đúng thời điểm; DHCP/reused IP không phải
danh tính cố định. Hai hệ dùng ID khác nhau cần key tương ứng, không join chỉ bằng số ID giống nhau.
Khi chỉ có metadata, viết claim ở mức metadata; không bịa HTTP body hay DNS từ event ứng dụng.

## Hypothesis và hành động tiếp theo

Với beacon/tunnel: so update/backup/telemetry và baseline cùng vai; periodicity/port/private IP không tự
quyết định. Với exfil: tách attempted connection, established flow, transferred bytes và content/recipient có
chứng cứ. Kiểm dữ liệu bị đọc/staged bên endpoint nếu câu hỏi là mất thông tin; không suy nội dung từ volume.
Với service disruption: kiểm server/app/health và đường mạng; packet loss ở sensor không chứng minh DDoS.

Export evidence hẹp có packet/frame/stream/record locators, query/filter/time range, counts và coverage.
IR nhận đích/lớp ngăn chặn hẹp, shared-service dependencies và điều cần verify; CNT nhận đặc trưng và benign
control. Không tự block/reset sessions ở role phân tích. PCAP/sample extracts không tự gửi lên dịch vụ ngoài.

Ca kiểm: hai sensors ghi một flow; NAT nhiều users; HTTPS không giải mã; DNS NXDOMAIN; sensor drop;
long backup giống exfil. Báo cáo cần nói rõ phần confirmed/unknown và phép kiểm tiếp theo.

Nguồn: [Zeek conn.log](https://docs.zeek.org/en/current/reference/logs/conn.html),
[Suricata EVE](https://docs.suricata.io/en/latest/output/eve/eve-json-output.html).
Tra schema đúng bản cài; đường dẫn latest có thể mô tả bản phát triển.
