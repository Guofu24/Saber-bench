# IR · Lưu lượng mạng độc hại, exfiltration và quy kết thủ phạm

## Phân tích lưu lượng mạng liên quan đến hoạt động độc hại

Kết hợp PCAP với log Firewall, Proxy và SIEM để xác định **kênh liên lạc** của attacker và **dữ liệu bị đưa ra
ngoài**. Đầu ra: kênh C2 và bằng chứng exfiltration (nếu có).

**Đọc PCAP tìm kênh độc**
1. Liệt kê hội thoại (endpoint, cổng, giao thức, bytes, thời lượng); bỏ hội thoại nội bộ và dịch vụ hạ tầng đã biết.
2. Đối chiếu DNS/HTTP/TLS: domain mới đăng ký/DGA/subdomain dài; SNI/Host header; User-Agent lạ; URI cố định lặp lại
   (`/gate.php`, `/api/beacon`).
3. **Tách kênh điều khiển:** C2 có chu kỳ đều + payload nhỏ hai chiều (lệnh/đáp), khác kênh tải về một chiều lớn.
4. IOC chỉ gồm IOC **của kênh độc** — không đưa domain CDN/phần mềm hợp lệ cùng xuất hiện trong PCAP.
5. Gắn **tiến trình** mở kết nối (netconn endpoint).

**Có exfiltration không — ba mức**

| Mức | Khi nào |
|---|---|
| `đã_bị_trích_xuất` | có bằng chứng dữ liệu đã ra: tệp tách từ luồng mạng chứa dữ liệu nhạy cảm/archive staging, phiên upload hoàn tất tới đích ngoài |
| `có_nguy_cơ` | attacker có truy cập dữ liệu và có kênh ra, lượng ra bất thường, nhưng **không xác nhận được nội dung** (mã hoá, không tách được). **"Không loại trừ" là kết luận IR hợp lệ.** |
| `không_có_bằng_chứng` | không thấy kênh hay lượng dữ liệu ra bất thường |

Ước lượng **tổng byte gửi ra** (`bytes_out`) trên các phiên của kênh exfil/C2 đã xác định.

```json
{"c2_conns": [{"ip": "198.51.100.4", "port": 443, "process": "rundll32.exe"}],
 "ioc": {"domain": ["upd-check.example-cdn.net"], "url": ["https://198.51.100.4/gate.php"]},
 "exfil_verdict": "có_nguy_cơ", "bytes_out": 48230000, "evidence": ["…"]}
```

## Truy tìm thủ phạm (quy kết nhóm tấn công)

Phân tích nguồn gốc và động cơ tấn công, đối chiếu kho dữ liệu APT của TI (APT41, APT40, APT32 và các nhóm khác).
Dựa vào **dấu hiệu đặc trưng** — TTP, công cụ, hạ tầng, "văn phong" — để xác định tên nhóm. Đầu ra: nhận định về
nhóm tấn công và động cơ.

**Quy trình quy kết thận trọng**
1. Ánh xạ hành vi quan sát được sang technique ATT&CK (`../../soc-hunt/reference/ttp-actor.md`).
2. So với hồ sơ TTP từng nhóm: chỉ tính phần **trùng có tính phân biệt** — công cụ/mã độc riêng của nhóm, hạ tầng tái
   sử dụng, chuỗi kỹ thuật đặc trưng, cách đặt tên/cấu hình. Technique phổ biến mà nhóm nào cũng dùng (`T1059`,
   `T1071`, `T1105`) **không** chứng minh danh tính.
3. Kiểm theo mô hình **Diamond** (adversary · infrastructure · capability · victim): quy kết cần ít nhất hai đỉnh độc
   lập cùng trùng khớp.
4. **Không đủ căn cứ ⇒ kết luận `khong_du_can_cu_quy_ket`.** Quy kết bừa là rủi ro nghiệp vụ thật (ảnh hưởng pháp lý,
   quan hệ với khách hàng).
5. Luôn nộp kèm **tập TTP làm căn cứ** cho kết luận. Nêu tên nhóm mà không chỉ ra được TTP trùng khớp là đoán tên,
   không phải suy ra.
6. Dùng tên/alias trong **bảng alias** của TI (vd APT41 = Winnti = Barium theo bảng nguồn).

```json
{"apt_group": "khong_du_can_cu_quy_ket", "ttps": ["T1190", "T1059.001", "T1071.001"],
 "rationale": "chỉ trùng technique phổ biến; không có công cụ/hạ tầng đặc trưng của nhóm nào"}
```

## Sai lầm thường gặp

- Đưa mọi domain/IP trong PCAP vào IOC, kể cả CDN/phần mềm hợp lệ.
- Kết luận "không exfil" khi chỉ là không giải mã được nội dung — đúng phải là "có nguy cơ".
- Quy kết APT dựa trên technique phổ biến; ép ra tên nhóm khi bằng chứng mỏng.
- Nêu tên nhóm mà không kèm TTP căn cứ.

Nguồn nghiệp vụ: NICE T1323, T1090 (catalog SABER).
