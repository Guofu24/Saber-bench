# IR · Lưu lượng mạng độc hại, exfiltration và quy kết thủ phạm

## Phân tích lưu lượng mạng liên quan đến hoạt động độc hại

Kết hợp PCAP với log Firewall, Proxy và SIEM để xác định **kênh liên lạc** của attacker và **dữ liệu bị đưa ra
ngoài**. Đầu ra: kênh C2 và bằng chứng exfiltration (nếu có).

**Đọc PCAP tìm kênh độc**
1. Liệt kê hội thoại (endpoint, cổng, giao thức, bytes, thời lượng); xét cả nội bộ và dịch vụ quen trong phạm vi.
   Chỉ loại lưu lượng khi có ngữ cảnh xác nhận hợp lệ, không chỉ vì private IP hoặc cổng phổ biến.
2. Đối chiếu DNS/HTTP/TLS: domain mới đăng ký/DGA/subdomain dài; SNI/Host header; User-Agent lạ; URI cố định lặp lại
   (`/gate.php`, `/api/beacon`).
3. **Tách kênh điều khiển:** chu kỳ và payload hai chiều là đầu mối; C2 có thể không đều hoặc cùng kênh truyền dữ liệu.
   Liên kết phiên với tiến trình, cấu hình mẫu và chuỗi hành vi; không bắt buộc một hình dạng lưu lượng cố định.
4. IOC chỉ gồm IOC **của kênh độc** — không đưa domain CDN/phần mềm hợp lệ cùng xuất hiện trong PCAP.
5. Gắn **tiến trình** mở kết nối (netconn endpoint).

**Có exfiltration không — ba mức**

| Mức | Khi nào |
|---|---|
| `đã_bị_trích_xuất` | có bằng chứng dữ liệu đã ra: tệp tách từ luồng mạng chứa dữ liệu nhạy cảm/archive staging, phiên upload hoàn tất tới đích ngoài |
| `có_nguy_cơ` | attacker có truy cập dữ liệu và có kênh ra, lượng ra bất thường, nhưng **không xác nhận được nội dung** (mã hoá, không tách được). **"Không loại trừ" là kết luận IR hợp lệ.** |
| `không_có_bằng_chứng` | không thấy kênh hay lượng dữ liệu ra bất thường |

Ước lượng **tổng byte gửi ra** (`bytes_out`) trên các phiên đã xác định; ghi điểm quan sát, chiều, cửa sổ thời gian,
NAT và cách loại trùng/retransmission. Bytes trên dây không tự bằng dung lượng dữ liệu nhạy cảm đã mất.
`không_có_bằng_chứng` chỉ nói về dữ liệu đã quan sát; PCAP thiếu/mã hoá không đủ để khẳng định không exfil.

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
3. Dùng **Diamond** (adversary · infrastructure · capability · victim) để tổ chức giả thuyết. Không có ngưỡng
   "hai đỉnh" bảo đảm quy kết đúng. Cần bằng chứng độc lập có tính phân biệt, xét hạ tầng/tool dùng chung,
   nguồn TI/thời điểm, giả thuyết khác và mức tin cậy.
4. **Không đủ căn cứ ⇒ kết luận `khong_du_can_cu_quy_ket`.** Quy kết bừa là rủi ro nghiệp vụ thật (ảnh hưởng pháp lý,
   quan hệ với khách hàng).
5. Luôn nộp kèm **tập TTP làm căn cứ** cho kết luận. Nêu tên nhóm mà không chỉ ra được TTP trùng khớp là đoán tên,
   không phải suy ra.
6. Dùng tên/alias theo **bảng alias của nguồn TI được cấp**; tên theo hãng có thể chỉ chồng lấn, không tự coi là đồng nhất ngoài phạm vi bảng.

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
