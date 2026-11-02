# MON · Phát hiện tấn công, lưu lượng bất thường và mối đe doạ tới tài sản

## Phát hiện tấn công và xâm nhập

Các nhóm hành vi bạn phải nhận ra (cũng là danh mục giám sát để gán `behavior_group`): **dò quét cổng ·
brute force · DoS · email phishing · mã độc · khai thác lỗ hổng web và hệ điều hành · kết nối tới IP/domain
độc hại · chiếm quyền máy chủ · thực thi câu lệnh độc hại**. Kết quả của việc phát hiện: cảnh báo được xác
nhận là sự cố và có ticket.

### Đọc log web để tìm request khai thác

Giải mã URL-encoding trước, rồi đánh giá từng request:

| Kiểu | Dấu hiệu | Không nhầm với |
|---|---|---|
| SQLi | **tổ hợp** token: `' or 1=1`, `union select`, `'--`, `sleep(`, `benchmark(`, `information_schema` | một từ SQL trong ngữ cảnh thường (`?q=select your plan`) |
| XSS | `<script`, `onerror=`, `javascript:` trong tham số | nội dung HTML hợp lệ do CMS gửi |
| Path traversal / LFI | `../`, `%2e%2e/`, `/etc/passwd`, `php://filter` | đường dẫn tĩnh hợp lệ |
| Command injection / RCE | `;`, `\|`, `$(`, backtick ghép lệnh hệ thống (`id`, `whoami`, `wget`) | ký tự đặc biệt trong ô tìm kiếm |
| Upload webshell | POST tới endpoint upload với script phía server (`.php .aspx .jsp`) | triển khai script được phép (`health.php`, `status.aspx`) |

Một request khai thác vẫn là attempt dù phản hồi là 403/404 — ghi nhận nó, nhưng thành công và tác động được
đánh giá riêng (xem nhóm `WEB_APP_EXPLOIT` trong `alert-groups.md`).

Khi có thêm log AD và các nguồn khác cùng khung giờ: nối các mảnh thành một nhận định — **có tấn công thật
không** (`is_attack`), **thuộc nhóm hành vi nào** (`behavior_group`), **đường vào** (`vector`: web, email, dịch vụ
phơi ra ngoài, thông tin đăng nhập hợp lệ…). Mỗi khẳng định kèm ID bản ghi.

```json
{"exploit_lines": [17, 42, 43], "is_attack": "yes", "behavior_group": "khai thác lỗ hổng web",
 "vector": "web", "evidence": ["…"]}
```

## Phân tích bất thường lưu lượng mạng (C2, tunneling)

Rà kết nối outbound tìm kết nối tới IP/domain độc hại — đặc biệt **máy chủ C2** — và dấu hiệu **tunneling**.

**Nhận diện beacon C2**
1. Gom kết nối theo (host nguồn, IP đích, cổng); tính khoảng cách thời gian giữa các kết nối liên tiếp.
2. Beacon thường có: **chu kỳ đều, jitter thấp**; kích thước gói nhỏ, ổn định; kéo dài; đích **hiếm** (ít host
   khác nói chuyện cùng); tiến trình không phải trình duyệt hay dịch vụ đã biết.
3. **Lưu lượng nền cũng có chu kỳ đều**: NTP (udp/123 tới máy chủ thời gian), telemetry của hãng, health-check.
   Đều đặn **không đủ** — cần đối chiếu ngữ cảnh, tiến trình, dữ liệu và hành vi. C2 có thể dùng trình duyệt,
   dịch vụ quen hoặc nhịp không đều; không coi "đích lạ + process lạ" là điều kiện bắt buộc.
4. Gắn **tiến trình** mở kết nối (netconn endpoint khớp theo ip, port, thời gian) — không biết tiến trình thì
   chặn sai chỗ.
5. Ước lượng **chu kỳ beacon** (trung vị khoảng cách).
6. Kiểm **vi phạm phân vùng** theo sơ đồ mạng: vùng người dùng nói thẳng ra internet không qua proxy, DMZ gọi
   vào vùng core.

```json
{"c2_conns": [{"ip": "203.0.113.9", "port": 8443, "process": "rundll32.exe"}],
 "beacon_period": 60, "zone_violation": [{"src": "ws-hr-03", "dst": "203.0.113.9"}], "evidence": ["…"]}
```

## Mối đe doạ tới tài nguyên mạng — săn liên thông

Khi phát hiện chiến dịch, săn IOC trên các tenant **đã được cấp phạm vi liên thông**. Chỉ chuyển chỉ dấu được phép
chia sẻ, không chuyển case/log/danh tính của khách hàng khác. Thiếu quyền thì bàn giao operator; mỗi tenant có
truy vấn, bằng chứng và báo cáo riêng. Đầu ra: tài sản đang bị nhắm tới trong phạm vi được giao.

1. **Host bị dò quét:** host **đích** nhận kết nối từ một nguồn tới nhiều cổng/nhiều lần bị chặn trong thời
   gian ngắn. Liệt kê **nạn nhân**, không phải nguồn quét.
2. **Xếp hạng mức đe doạ:** cường độ bị nhắm (số nguồn, số cổng, có khai thác tiếp không) × **giá trị tài sản**
   (cấp độ, core, VIP, phơi ra internet, lỗ hổng đang mở). Xếp từ nguy cơ cao nhất xuống.
3. **Nối cảnh báo rời rạc thành chiến dịch:** cùng hạ tầng nguồn, cùng TTP, cùng khung thời gian, chuỗi quét →
   khai thác → đăng nhập. Kết luận có/không cùng chiến dịch (`campaign_link`).
4. **Loại scanner nội bộ hợp lệ** (đúng nguồn, đúng lịch) khỏi danh sách bị nhắm.

```json
{"scanned_hosts": ["web-01", "vpn-gw", "mail-01"],
 "targeted": ["web-01", "vpn-gw"], "ranking": ["vpn-gw", "web-01"], "campaign_link": "yes",
 "evidence": ["…"]}
```

## Sai lầm thường gặp

- Coi một từ SQL đơn lẻ hay ký tự đặc biệt hợp lệ là tấn công.
- Coi mọi kết nối đều đặn là beacon (NTP, telemetry).
- Liệt kê nguồn quét thay vì host bị quét; quên loại scanner nội bộ hợp lệ.

Nguồn nghiệp vụ: NICE T1347, T1386, T1085 (catalog SABER).
