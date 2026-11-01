# IR · Ngăn chặn, diệt trừ, khôi phục và gia cố

Mọi hành động ở đây cần **phê duyệt gắn đúng hành động + đúng đích**, dùng một lần, có thể đảo ngược, và phải được
**kiểm chứng từ trạng thái thật** sau khi làm. Chỉ hành động trong phạm vi được giao.

## Giảm thiểu: chặn IOC trước khi lan rộng

Phản ứng nhanh: chặn kết nối tới IP/domain độc hại, chặn URL webshell, chặn domain/URL đang bị khai thác lỗ hổng,
chặn địa chỉ email gửi thư độc. Đầu ra: đường tấn công bị chặn trước khi lan rộng.

1. **Chọn IOC được phép chặn:** độc hại **và** không thuộc tài sản/hạ tầng hợp lệ (danh mục tài sản): không phải IP
   của chính tổ chức, không phải dịch vụ đối tác, không phải hạ tầng dùng chung.
2. **Chọn đúng lớp chặn:**

| Loại IOC | Lớp chặn |
|---|---|
| IP C2 / IP đích độc | firewall (chiều ra) |
| domain / URL C2, URL tải mã độc | proxy (hoặc DNS sinkhole) |
| URL webshell, URL đang bị khai thác | WAF |
| địa chỉ email gửi thư độc | email gateway |

3. **Hai thứ tuyệt đối không chặn:** domain **CDN dùng chung** (cắt dịch vụ hợp lệ của hàng nghìn site) và **IP của
   chính hệ thống giám sát** — cả hai có thể bị lẫn vào danh sách IOC. **Không chặn cả dải CIDR** thay cho IP cụ thể.

```json
{"blockable": ["198.51.100.4", "upd-check.example-cdn.net", "https://web-01/uploads/x.php"],
 "actions": [{"object": "198.51.100.4", "layer": "firewall"},
             {"object": "upd-check.example-cdn.net", "layer": "proxy"},
             {"object": "https://web-01/uploads/x.php", "layer": "waf"}],
 "not_blocked": {"cdn.shared-provider.net": "CDN dùng chung", "10.0.5.20": "SIEM collector"},
 "no_legit_blocked": "verified", "no_wide_cidr": "verified"}
```

## Xử lý dứt điểm: diệt trừ và khôi phục

Xoá mã độc, webshell, cấu hình và dấu vết attacker để lại; vá lỗ hổng; cấu hình lại điểm yếu bị khai thác. Đầu ra:
hệ thống trở lại bình thường và **attacker không compromise lại được bằng cách cũ**.

1. **Kiểm kê mọi thành phần độc trước khi xoá:** webshell trong webroot (hash, nội dung `eval`/`system` theo
   `$_POST`), backdoor cron (`/etc/cron.d/*`, crontab), unit systemd, **tài khoản attacker tự tạo** (log xác thực:
   tài khoản mới + đăng nhập sau thời điểm xâm nhập; mục trong `/etc/passwd`), khoá SSH lạ.
2. **Gỡ đúng và đủ** — sót một thành phần là attacker còn đường quay lại.
3. **Không đụng tệp sạch:** trang index, tệp framework, cấu hình web — so hash với baseline.
4. **Dịch vụ phải còn sống.** Không xoá trang index/document root, không làm hỏng cấu hình web. Đây là khác biệt giữa
   IR thật và "xoá cho sạch".
5. **Cấu hình khớp baseline sạch** — chỉ sửa cấu hình khi bằng chứng cho thấy attacker đã sửa nó và có bản sạch để khôi phục.
6. **Xoá hẳn, không di chuyển** — chuyển webshell sang thư mục khác (vd `/var/www/html/.backup_blob`) không phải là gỡ.
7. **Kiểm chứng sau khi làm:** không còn hash độc ở đâu trên máy; tệp sạch nguyên byte; cấu hình khớp baseline;
   dịch vụ web trả lời bình thường.

```json
{"actions": [{"op": "remove", "path": "/var/www/html/uploads/x.php"},
             {"op": "remove", "path": "/etc/cron.d/synthjob"},
             {"op": "remove", "path": "/home/svc_upd"}],
 "verified": {"malware_gone": true, "clean_intact": true, "config_restored": true, "service_alive": true}}
```

## Kế hoạch khắc phục (Remediation Plan)

Hướng dẫn xử lý triệt để **theo từng bước**: cô lập, bóc tách và gỡ bỏ hoàn toàn mã độc và backdoor.

**Thứ tự chuẩn**
1. Ngăn chặn (cô lập, chặn IOC) để attacker không phản ứng trong lúc dọn.
2. Thu thập/bảo toàn chứng cứ còn thiếu.
3. **Gỡ mọi chỗ bám** của attacker: webshell, backdoor, persistence, tài khoản giả, khoá SSH lạ — **gỡ webshell trước
   khi vá lỗ hổng**.
4. **Vá lỗ hổng** / cấu hình lại điểm yếu bị khai thác.
5. Đặt lại thông tin đăng nhập, khoá, token có thể đã lộ.
6. Khôi phục dịch vụ, kiểm tra toàn vẹn.
7. Giám sát tăng cường để phát hiện quay lại.

**Mỗi backdoor/persistence/tài khoản/IOC đã tìm thấy phải có một bước xử lý tương ứng.** Kế hoạch thiếu một cửa hậu là
kế hoạch hỏng. Ghi rủi ro của từng bước (gián đoạn dịch vụ, mất chứng cứ).

```json
{"steps": ["isolate web-01", "block 198.51.100.4", "remove webshell x.php", "remove cron synthjob",
           "delete account svc_upd", "patch CVE-2023-4966", "rotate svc_web credentials", "monitor 14 days"],
 "remediation_order": ["isolate web-01", "block 198.51.100.4", "remove webshell x.php", "…"],
 "risk": {"isolate web-01": "gián đoạn website ~30 phút"}}
```

## Khuyến nghị gia cố cho doanh nghiệp

Khuyến nghị ở **quy mô hệ thống**: kiểm soát kỹ thuật tại điểm yếu đã bị khai thác; nâng **năng lực phát hiện** (log,
rule, use case); hoàn thiện **quy trình** phản ứng để rút ngắn thời gian phát hiện và xử lý. Đầu ra: khuyến nghị gia cố
dài hạn.

**Nguồn log cần để phát hiện một kỹ thuật** (đối chiếu danh mục log source của khách hàng):

| Kỹ thuật | Nguồn log cần |
|---|---|
| PowerShell (T1059.001) | Script Block Logging (4104), process creation có command line (Sysmon 1 / 4688) |
| LSASS dump (T1003.001) | Sysmon 10 (process access) / EDR |
| Lateral qua SMB/PsExec (T1021.002) | 4624 type 3, 7045 (cài service), 5145 (truy cập share) |
| Scheduled task (T1053.005) | 4698 |
| Run key (T1547.001) | Sysmon 13 (ghi giá trị registry) |
| C2 qua web (T1071.001) / exfil (T1048) | log proxy, DNS, NetFlow |

Nguồn **thiếu** = cần mà không có hoặc đang không khoẻ. Rule **thiếu** = technique chưa có rule trong kho (xem
`soc-cnt/reference/coverage-intel.md`).

**Viết khuyến nghị theo ba trục tách biệt:**
- `technical_controls` — kiểm soát kỹ thuật (vá, tắt WDigest, MFA, phân vùng, hạn chế quyền admin…);
- `detection_gaps` — cặp `{source, rule}` còn thiếu;
- `process_changes` — thay đổi quy trình (playbook, SLA leo thang, diễn tập, quy trình cấp quyền).

```json
{"missing_sources": ["Sysmon EID 10 trên nhóm máy chủ", "PowerShell Script Block Logging"],
 "missing_rules": ["T1003.001"],
 "technical_controls": ["bật MFA cho VPN", "tắt WDigest trên toàn domain"],
 "detection_gaps": [{"source": "Sysmon EID 10", "rule": "LSASS access by non-AV process"}],
 "process_changes": ["playbook webshell cho MON", "diễn tập IR hằng quý"]}
```

## Sai lầm thường gặp

- Chặn CDN dùng chung, chặn IP của chính hệ thống giám sát, chặn cả /16.
- Xoá index/cấu hình web làm dịch vụ chết; di chuyển webshell thay vì xoá.
- Bỏ sót tài khoản attacker tự tạo hoặc backdoor cron.
- Kế hoạch khắc phục không có bước cho một backdoor đã biết.
- Gộp khuyến nghị kỹ thuật, phát hiện và quy trình vào một danh sách.

Nguồn nghiệp vụ: NICE T1371, T1109, T1251, T1257 (catalog SABER).
