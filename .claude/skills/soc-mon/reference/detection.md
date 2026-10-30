# MON · Phát hiện — T1347 (tấn công/xâm nhập) · T1386 (bất thường mạng) · T1085 (mối đe doạ tới tài nguyên)

---

## T1347 — Phát hiện các cuộc tấn công và xâm nhập

Tier 1 phân tích các **nhóm cảnh báo tấn công** (đây cũng là danh mục `behavior_group`): dò quét cổng ·
brute force · DoS · email phishing · mã độc · khai thác lỗ hổng web và hệ điều hành · kết nối tới
IP/domain độc hại · chiếm quyền máy chủ · thực thi câu lệnh độc hại. Đầu ra: cảnh báo được xác nhận là
sự cố + ticket. SLA: Nghiêm trọng/Cao ≤ 30′, Trung bình ≤ 1h, đúng hạn ≥ 90%.

| Subtask | Mode | Đầu vào | Phải nộp | Chấm |
|---|---|---|---|---|
| **T1347.001** | file | HV-28 log web N dòng | `exploit_lines[]` | set_delta (dòng) |
| **T1347.002** | file | HV-26, HV-28 | `exploit_lines[]`, `behavior_group` | 0.6 / 0.4 |
| **T1347.003** | soc (SIEM, EDR, NSM/IDS) | HV-01 02 15 21 22 26 28 | `is_attack`, `behavior_group`, `vector`, `citations[]` | 0.35 / 0.25 / 0.25 / **0.15 trích dẫn** |

**Đọc log web để liệt kê dòng khai thác (.001/.002)** — `exploit_lines` là ID/số dòng (chuẩn hoá về số
nguyên), set_delta ⇒ mỗi dòng lành tính báo nhầm trừ nặng.
- SQLi: **tổ hợp** token (`' or 1=1`, `union select`, `'--`, `sleep(`, `benchmark(`, `information_schema`)
  — một từ SQL đơn lẻ trong ngữ cảnh bình thường (`?q=select your plan`) là **lành tính**.
- XSS: `<script`, `onerror=`, `javascript:` trong tham số.
- Path traversal / LFI: `../`, `%2e%2e/`, `/etc/passwd`, `php://filter`.
- Command injection / RCE: `;`, `|`, `$(`, backtick ghép với lệnh hệ thống (`id`, `whoami`, `wget`).
- Upload webshell: POST tới endpoint upload với tên script phía server (`.php/.aspx/.jsp`).
- Payload không cần thành công mới tính là *dòng khai thác*; giải mã URL-encoding trước khi đánh giá.

**.002** thêm log AD để gán `behavior_group` của cả gói (một giá trị trong danh mục giám sát ở trên).

**.003 — gói cảnh báo đa nguồn một khung giờ:** `is_attack` (có tấn công thật không), `behavior_group`,
`vector` (đường vào: web, email, dịch vụ phơi ra ngoài, thông tin đăng nhập…). **Mọi khẳng định phải
kèm trích dẫn grep được** — ở đây trích dẫn là mục có trọng số 0.15, trích ID bịa vẫn làm mất điểm mục đó.

Live lab của SABER chấm thật `T1347.001` trên telemetry loopback (họ `web_sqli_probe`, `fs_change`,
`persistence`, `auth_bruteforce`) — có nhiễu client lành tính và hard negative (SQL-word, file được
phép như `health.php`, job `logrotate`).

---

## T1386 — Phân tích bất thường lưu lượng mạng

Rà kết nối outbound tìm kết nối tới IP/domain độc hại — đặc biệt **máy chủ C2** — và dấu hiệu **network
tunneling**. Đầu ra: danh sách kết nối C2 và kênh tunneling.

| Subtask | Mode | Đầu vào | Phải nộp | Chấm |
|---|---|---|---|---|
| **T1386.001** | file | HV-22 conn.log | `c2_conns[]` `{ip, port}` | set_delta |
| **T1386.002** | file | HV-17, HV-22 | `c2_conns[]` `{ip, port, process}` | F1, **sai tiến trình = 0.5 phần tử** |
| **T1386.003** | soc (NSM, EDR, SIEM) | HV-17 22 23 27 37 38 (NetFlow 14 ngày) | `c2_conns[]` `{ip,port,process}`, `beacon_period`, `zone_violation[]` `{src,dst}` | 0.6 / 0.2 (±20%) / 0.2 |

**Nhận diện beacon C2**
1. Gom theo (host nguồn, IP đích, cổng). Tính khoảng thời gian giữa các kết nối liên tiếp.
2. Beacon: **chu kỳ đều, jitter thấp**, kích thước gói nhỏ và ổn định, kéo dài, đích **hiếm** (ít host
   khác cùng nói chuyện), tiến trình không phải trình duyệt/dịch vụ đã biết.
3. **Mẫu âm bắt buộc ở .003: lưu lượng nền cũng có chu kỳ đều** — NTP (udp/123 tới máy chủ thời gian),
   telemetry của hãng, health-check. Tính đều đặn **không** đủ; phải cộng đích lạ + tiến trình lạ +
   không nằm trong danh mục dịch vụ hợp lệ.
4. `process` ở .002/.003: lấy từ netconn endpoint (HV-17) khớp theo (ip, port, thời gian). Sai tiến
   trình chỉ còn nửa điểm — và ngoài đời là chặn sai chỗ.
5. `beacon_period`: chu kỳ trung vị (đơn vị theo input), dung sai ±20%.
6. `zone_violation[]`: cặp {src, dst} vi phạm phân vùng trong sơ đồ HV-37 (vd vùng user nói thẳng ra
   internet không qua proxy, vùng DMZ gọi vào vùng core).

---

## T1085 — Nhận diện mối đe doạ tiềm tàng tới tài nguyên mạng

Cơ chế **phản ứng liên thông**: khi phát hiện tấn công nhắm vào một khách hàng, lập tức săn IoC trên
toàn bộ hệ sinh thái khách hàng còn lại. Đầu ra: danh sách tài sản/khách hàng khác có cùng dấu hiệu bị
nhắm tới. Hunting liên tục 24/7, kích hoạt ngay khi có tình báo chiến dịch mới.

| Subtask | Mode | Đầu vào | Phải nộp | Chấm |
|---|---|---|---|---|
| **T1085.001** | file | HV-27 log firewall | `scanned_hosts[]` | set_delta (host) |
| **T1085.002** | file | HV-27, HV-38 | `targeted[]`, `ranking[]` | 0.7·F2 + 0.3·max(0, ρ) |
| **T1085.003** | soc (SIEM, Quản lý lỗ hổng) | HV-01 02 06 12 26 27 28 38 (7 ngày, 40 tài sản) | `targeted[]`, `ranking[]`, `campaign_link`, `citations[]` | (0.6·F2 + 0.2·ρ + 0.2·link) × CITE |

- **.001 host bị dò quét:** host **đích** nhận kết nối từ một nguồn tới nhiều cổng/nhiều lần bị từ chối
  trong thời gian ngắn (log deny/SYN không hoàn tất). Liệt kê nạn nhân, không liệt kê nguồn quét.
- **.002 xếp hạng mức đe doạ:** kết hợp cường độ bị nhắm (số nguồn, số cổng, có khai thác tiếp không)
  với **giá trị tài sản** trong HV-38 (cấp độ, core, VIP, phơi ra internet, lỗ hổng mở trong HV-12).
  `ranking` là danh sách host xếp từ nguy cơ cao nhất; chấm bằng Spearman ρ — liệt kê đủ.
- **.003 nối cảnh báo rời rạc thành một chiến dịch:** cùng hạ tầng nguồn, cùng TTP, cùng khung thời
  gian, chuỗi quét → khai thác → đăng nhập. `campaign_link` = có/không cùng chiến dịch (theo `options`).
  **Bẫy FP: 4 tài sản bị scanner nội bộ quét hợp lệ** — đối chiếu nguồn với danh mục scanner/lịch quét,
  loại chúng khỏi `targeted`. Gate CITE: mọi tài sản đưa vào phải có bản ghi thật chống lưng.

## Bẫy hay gặp

- Báo một từ SQL đơn lẻ là khai thác; báo cả dòng có ký tự đặc biệt hợp lệ.
- Coi mọi kết nối đều đặn là beacon (NTP, telemetry).
- Liệt kê nguồn quét thay vì host bị quét.
- Không loại scanner nội bộ hợp lệ khỏi danh sách bị nhắm.
