# CNT · Viết rule và chữ ký — T0020 (nội dung cho công cụ phòng thủ) · T1406 (chữ ký YARA/Suricata/parser)

---

## T0020 — Xây dựng nội dung (rule/chữ ký) cho công cụ phòng thủ mạng

Xây dựng và tái cấu trúc tập rule/use-case cho SIEM **theo chuẩn VCS**; tối đa 5 use-case/tháng (gói
Advanced), đóng gói theo phiên bản release. Benchmark cần kiểm thêm content liên quan tới sản phẩm VCS.

| Subtask | Mode | Đầu vào | Phải nộp | Chấm |
|---|---|---|---|---|
| **T0020.001** | file | HV-02 log N dòng (M dòng là kỹ thuật cần bắt) | `rule` `{engine:"regex", pattern, ignore_case}` | **set_delta** `max(0, M′/M − N′/(N′+M′))` — verifier chạy rule rồi đếm |
| **T0020.002** | soc (SIEM) | HV-02, HV-05 | `rule` theo chuẩn SIEM đích + `technique` ATT&CK | 0.8 exec + 0.2 enum |
| **T0020.003** | soc (SIEM) | HV-02 04 05 32 33 | `rule` | `max(0, TPR − FPR) × [parse_ok]` — corpus **200.000 dòng**, P = 50 sự kiện dương, nền chọn loại dễ khớp nhầm |

**Quy trình viết rule phát hiện**
1. **Tách dòng dương** trong corpus công khai: đọc kỹ M dòng kỹ thuật cần bắt, rút ra điểm chung *bản
   chất* (tổ hợp token, cấu trúc lệnh, cặp trường).
2. **Liệt kê hard negative** cùng bề mặt: dòng chứa một phần token đó trong ngữ cảnh lành tính. Ở live
   lab: request có từ SQL nhưng không phải tổ hợp tấn công; upload `health.php/status.aspx` được phép;
   job `backup/logrotate` hợp lệ.
3. **Viết pattern hẹp nhất bắt đủ dương**, kiểm tay trên cả hai tập. set_delta phạt FP rất nặng: 1 FP
   trên 10 dương đã mất ~0.09, 10 FP mất một nửa.
4. **T0020.002 — chuẩn SIEM đích + ATT&CK:** viết theo cú pháp rule của SIEM đích ghi trong đề/HV-05
   (trên fixture DEV vẫn chạy bằng regex — xem `engines.md`); `technique` là ID ATT&CK (`T1190`,
   `T1059.001`…) khớp hành vi rule bắt, tra mapping trong HV-05.
5. **T0020.003 — corpus lớn:** điểm là TPR − FPR (không phải set_delta) nhân gate `parse_ok`. Trên
   200.000 dòng, FPR 0.5% đã là ~1.000 alert — vẫn phải hẹp. **Hiệu năng là yêu cầu chức năng:** pattern
   backtracking ⇒ timeout ⇒ 0.

---

## T1406 — Xây dựng chữ ký cho công cụ phòng thủ mạng

Thiết kế/tái cấu trúc tập rule built-in của SIEM, phát triển **parser và content pack chuyên biệt** cho
hệ thống nội bộ khách hàng. Đầu ra: tập rule chuẩn hoá, có quản trị vòng đời. SLA: tối đa 2 hệ thống/ứng
dụng mỗi quý, 5 mỗi năm.

| Subtask | Mode | Đầu vào | Phải nộp | Chấm |
|---|---|---|---|---|
| **T1406.001** | file | HV-18 (M mẫu cùng họ + N mẫu sạch) | `rule` YARA | F1 theo mẫu (verifier chạy luật trên cả hai tập) |
| **T1406.002** | file | HV-18, HV-34 | `rule` YARA | F1 — **nửa tập dương là biến thể đã đổi hash nhưng giữ hành vi** |
| **T1406.003** | soc (NSM/IDS) | HV-02 04 05 06 18 21 23 24 31 34 (đầu vào là **PCAP**) | `rule` chữ ký Suricata / parser | F1 (`exec/pcap`) |

**YARA tốt cho một họ mã độc (.001/.002)**
1. So các mẫu họ với nhau: tìm chuỗi **chung cho mọi mẫu họ** và **không có trong mẫu sạch** — chuỗi
   config/marker (`cfg=SynthBeacon;`), mutex, đường dẫn PDB, định dạng URL C2, chuỗi lỗi đặc thù.
2. Gold pilot T1406.001 cài **near-miss**: một công cụ sạch mang `cfg=SynthBackup;v=3;` — cùng khung với
   marker họ `cfg=SynthBeacon;v=3;`. Khớp phần **tên họ**, không khớp khung `cfg=…;v=3;`.
3. **.002 — không bám hash:** biến thể đổi hash giữ hành vi ⇒ luật dựa hash/bytes ngẫu nhiên rớt recall
   ~0.5. Dùng HV-34 (báo cáo phân tích mã độc) lấy đặc điểm hành vi/cấu hình bền vững.
4. Điều kiện kết hợp ≥2 chuỗi độc lập (`$a and $b`) để giảm FP; định dạng `yara_subset` ở `engines.md`.

**Chữ ký mạng từ PCAP (.003)**
1. Tách phiên độc trong PCAP (HV-24), đối chiếu cảnh báo NSM (HV-21) và log DNS/HTTP/TLS (HV-23).
2. Chọn đặc điểm ổn định của giao thức C2/khai thác: URI path cố định, header bất thường (User-Agent
   đặc thù), cấu trúc body, JA3/SNI nếu có — không dùng IP đích làm điều kiện chính.
3. Tham khảo HV-06 (thống kê alert theo rule) để tránh viết lại một rule đã nhiễu; ghi ticket tối ưu
   (HV-11) nếu đụng rule cũ.
4. Với **parser** cho hệ thống nội bộ (HV-31 log ứng dụng): tách đúng trường (thời gian, nguồn, người
   dùng, hành động, kết quả) để rule phía sau dùng được.
5. Chữ ký Suricata thật chưa tích hợp (`BLOCKED_INTEGRATION`); fixture DEV chấm bằng regex.

## Bẫy hay gặp

- Bắt theo một từ khoá rộng (`select`, `cmd`, `cfg=`) ⇒ FP hàng loạt.
- Luật YARA dựa hash hoặc byte ngẫu nhiên.
- Rule đúng logic nhưng không parse được trên engine đích, hoặc timeout trên corpus lớn.
- Gán technique ATT&CK theo tên rule thay vì theo hành vi rule thực sự bắt.
