# IR · Lưu lượng mạng độc hại và quy kết — T1323 (phân tích lưu lượng) · T1090 (truy tìm thủ phạm)

---

## T1323 — Phân tích lưu lượng mạng liên quan đến hoạt động độc hại

Phân tích lưu lượng gắn với hoạt động độc hại, kết hợp log Firewall, Proxy và SIEM để xác định **kênh
liên lạc** và **dữ liệu bị đưa ra ngoài**. Đầu ra: kênh C2 và bằng chứng exfiltration (nếu có). Nguồn
review: benchmark nên là bài phân tích PCAP.

| Subtask | Mode | Đầu vào | Phải nộp | Chấm |
|---|---|---|---|---|
| **T1323.001** | file | HV-24 PCAP | `ioc{}` (IP, domain, URL) của kênh độc | F1 |
| **T1323.002** | file | HV-22, HV-24 | `ioc{}`, `c2_conns[]` `{ip, port}` | 0.5 / 0.5 |
| **T1323.003** | soc (NSM, SIEM) | HV-17 22 23 24 25 27 | `c2_conns[]` `{ip, port, process}`, `exfil_verdict`, `bytes_out` | 0.5 / 0.3 / 0.2 (±20%) |

**Đọc PCAP tìm kênh độc**
1. Liệt kê hội thoại (endpoint, cổng, giao thức, bytes, thời lượng); lọc bỏ hội thoại nội bộ và dịch vụ
   hạ tầng đã biết.
2. Đối chiếu DNS (HV-23): domain mới đăng ký/DGA/subdomain dài; SNI/Host header; User-Agent lạ; URI cố
   định lặp lại (`/gate.php`, `/api/beacon`).
3. **.002 — tách kênh điều khiển:** kênh C2 có chu kỳ đều + payload nhỏ hai chiều (lệnh/đáp), khác kênh
   tải về một chiều lớn. `c2_conns` là đầu xa `{ip, port}` của kênh điều khiển.
4. `ioc{}` chỉ gồm IOC **của kênh độc** — không đưa domain CDN/phần mềm hợp lệ cùng xuất hiện trong PCAP.

**.003 — có exfil không? Thang 3 mức** (dùng đúng nhãn của đề)
- `đã_bị_trích_xuất` — có bằng chứng dữ liệu đã ra: tệp tách từ luồng mạng (HV-25) chứa dữ liệu nhạy cảm/
  archive staging, phiên upload hoàn tất tới đích ngoài.
- `có_nguy_cơ` — attacker có truy cập dữ liệu và có kênh ra, lượng ra bất thường nhưng **không xác nhận
  được nội dung** (mã hoá, không tách được). **"Không loại trừ" là kết luận IR hợp lệ.**
- `không_có_bằng_chứng` — không thấy kênh/lượng ra bất thường.
- `bytes_out`: tổng byte gửi ra trên kênh exfil/C2 đã xác định (cộng các phiên liên quan; dung sai ±20%).
- `process` của `c2_conns`: tiến trình mở kết nối, khớp netconn endpoint (HV-17).

---

## T1090 — Xác định phương pháp tốt nhất để truy tìm thủ phạm

Phân tích nguồn gốc và động cơ tấn công, đối chiếu kho APT của Viettel TI (APT41, APT40, APT32 và các nhóm
khác). Dựa vào **dấu hiệu đặc trưng (TTP/văn phong)** để xác định tên nhóm. Đầu ra: nhận định về nhóm tấn
công và động cơ.

| Subtask | Mode | Đầu vào | Phải nộp | Chấm |
|---|---|---|---|---|
| **T1090.001** | file | HV-35 (danh sách TTP) | `apt_group` | enum **theo bảng alias** (vd APT41 = Winnti = Barium theo nguồn) |
| **T1090.002** | file | HV-34, HV-35 | `apt_group` | enum — **≥2 mẫu có đáp án đúng là `khong_du_can_cu_quy_ket`** |
| **T1090.003** | file | HV-04 15 23 26 27 32 34 35 36 | `apt_group`, `ttps[]` | 0.5 + 0.5, **cap 0.5 nếu tập TTP không giao với nhãn** |

**Quy trình quy kết thận trọng**
1. Ánh xạ hành vi quan sát được sang technique ATT&CK (`soc-hunt/reference/ttp-actor.md`).
2. So với hồ sơ TTP từng nhóm trong HV-35: đếm phần **trùng có tính phân biệt** — tool/malware riêng của
   nhóm, hạ tầng tái sử dụng, chuỗi kỹ thuật đặc trưng, "văn phong" (đặt tên, cấu hình). Technique phổ
   biến mọi nhóm đều dùng (`T1059`, `T1071`, `T1105`) **không** chứng minh danh tính.
3. Dùng mô hình Diamond (adversary · infrastructure · capability · victim) để kiểm quy kết có đủ ít nhất hai
   đỉnh độc lập trùng khớp không.
4. **Không đủ căn cứ ⇒ `khong_du_can_cu_quy_ket`.** Quy kết bừa là **rủi ro nghiệp vụ thật** (ảnh hưởng
   pháp lý/ngoại giao với khách hàng); đề cố ý có ≥2 mẫu như vậy.
5. **.003:** nộp `ttps[]` — tập technique **làm căn cứ** quy kết. Kết luận nhóm mà không nêu được TTP trùng
   khớp với nhãn là **đoán tên** ⇒ trần 0.5.
6. Tên nhóm: dùng tên/alias có trong bảng alias của đề.

## Bẫy hay gặp

- Đưa mọi domain/IP trong PCAP vào IOC, kể cả CDN/phần mềm hợp lệ.
- Kết luận "không exfil" khi chỉ là không giải mã được nội dung (đúng phải là `có_nguy_cơ`).
- Quy kết APT dựa trên technique phổ biến; ép tên nhóm khi bằng chứng mỏng.
- Nộp `ttps[]` không liên quan tới nhóm đã kết luận.
