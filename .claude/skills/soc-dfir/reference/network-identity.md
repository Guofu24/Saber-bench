# DFIR · Network, email và identity

Đầu ra là session/entity graph, activity timeline, scope/impact và khoảng không quan sát được.
Phân biệt identity, credential, session/token, application/service principal và người thật.

## Network

Nối host/process → DNS → flow/proxy → destination bằng cửa sổ giờ và định danh đủ mạnh.
Giữ 5-tuple, direction, start/end, NAT/VPN/DHCP mappings, interface/sensor vantage, byte semantics,
capture filter/drop counters và clock. Zeek UID là trong phạm vi nguồn; không gộp chỉ vì trùng IP/port.
TLS/ECH/QUIC, proxy bypass, asymmetric routing và packet loss có thể che nội dung/luồng.

| Quan sát | Kiểm thêm trước kết luận |
|---|---|
| DNS query đến domain có IOC | Response/cache, client/process, connection sau đó, feed age và baseline |
| Nhiều bytes outbound | Tính bytes ở đâu, backup/update/replication, file/object read/staging, nội dung nếu thấy |
| Kết nối định kỳ | Agent quản trị/SaaS hợp lệ, process owner/signature và activity lân cận |
| PCAP không có payload đọc được | Encryption/capture scope; không suy rằng không có truyền dữ liệu |
| DDoS/HTTP errors | Availability/mitigation timeline; điều tra intrusion riêng, không tự gán data breach |

Tshark/Suricata/Zeek là parser/sensor với cấu hình và coverage riêng. Rule alert là đầu mối;
giữ rule/version, raw packet/event refs và replay điều kiện hợp lệ; không coi alert là verdict.

## Email/BEC

Giữ message gốc (.eml/.msg nếu có), header/Received chain, provider trace IDs, sender/recipient,
URLs/attachment metadata cùng sign-in, mailbox rules/forwarding, delegates, OAuth consent và audit.
Đánh giá trust boundary của header: trường do sender tự đặt không tự thành bằng chứng đã được provider xác thực.
SPF/DKIM/DMARC pass không chứng minh nội dung hợp lệ. Sent/delivered khác read và khác thanh toán đã xảy ra.
Không click link/open attachment trực tiếp; chỉ phân tích sample qua lab được cấp.
Xác nhận business change/user bằng kênh tin cậy do case owner điều phối; không tự gửi thông báo ngoài nhiệm vụ.

## AD/Entra và session abuse

1. Xác định account SID/object ID, domain/tenant, privilege, device, session/logon IDs và thời gian.
2. AD: correlate DC auth/Kerberos 4768/4769/4771, NTLM validation 4776, endpoint logons,
   group/ACL/GPO/delegation, PKI/AD CS và sync logs khi triển khai. Admin logon không tự chứng minh forest compromise.
3. Entra/SaaS: sign-in/audit/risk/conditional access, MFA methods, devices, app consent/service principals,
   role assignments và hậu quả mailbox/file/resource. IP/ASN/geolocation quen lạ đều cần context VPN/proxy.
4. Theo credential/session → resource/action → downstream identities. Kiểm cùng source và quyền ở thời điểm đó,
   không dùng current permissions để thay lịch sử. Token bị chiếm có thể chạy từ device/IP quen.
5. Bàn giao identity/IR lựa chọn block/revoke/reset/grant removal/rotation theo dependency và scope đã cấp.
   Password reset không bảo đảm mọi session/token/app grant mất hiệu lực; cần audit/behavior xác minh.
   Không tự reset domain/forest, rotate hàng loạt hoặc xuất credential material.

## Kết luận và escalation

Phân loại access attempted, successful authentication, unauthorized action, data read/export và external receipt
riêng biệt. Bằng chứng user/token thực hiện action không chứng minh người sở hữu chủ động làm hoặc có ý đồ.
Nếu thiếu NAT mapping, audit policy hay data access logs: giữ unknown; mô tả nguồn cần bổ sung và owner.
OT/network appliance nghi bị chiếm cần nguồn ngoài thiết bị và owner vận hành; không reboot trước khi cân nhắc
volatile state, safety và management access. Quyết định response thuộc IR/owner theo quyền đã giao.

Tham chiếu: [Microsoft identity risk investigation](https://learn.microsoft.com/en-us/entra/id-protection/howto-identity-protection-investigate-risk),
[Purview audit search](https://learn.microsoft.com/en-us/purview/audit-search).
