# CNT · Viết rule và chữ ký mới

Xây dựng và tái cấu trúc tập rule/use-case cho SIEM **theo chuẩn VCS**, rule built-in của SIEM, **parser** và
**content pack** cho hệ thống nội bộ của khách hàng. Mọi rule đóng gói theo phiên bản release và có quản trị
vòng đời.

## Rule phát hiện trên log (SIEM)

**Quy trình**
1. **Tách mẫu dương:** đọc kỹ các dòng chứa kỹ thuật cần bắt; rút ra điểm chung **bản chất** (tổ hợp token,
   cấu trúc lệnh, cặp trường) chứ không phải giá trị cụ thể.
2. **Liệt kê mẫu âm cùng bề mặt:** dòng chứa một phần đặc điểm đó trong ngữ cảnh lành tính — request có từ SQL
   nhưng không phải tổ hợp tấn công; upload `health.php`/`status.aspx` được phép; job `backup`/`logrotate` hợp lệ.
3. **Viết pattern hẹp nhất bắt đủ mẫu dương**; kiểm tay trên cả mẫu dương lẫn mẫu âm. Mỗi FP mà rule sinh ra là
   thêm việc cho ca trực — 10 FP trên 10 TP nghĩa là một nửa cảnh báo là rác.
4. **Theo chuẩn SIEM đích**: viết bằng cú pháp rule của SIEM đó, gán **technique ATT&CK** đúng với hành vi rule
   thực sự bắt (tra mapping trong kho rule), không theo tên rule.
5. **Corpus lớn (hàng trăm nghìn dòng)**: hiệu năng là yêu cầu chức năng. Ở 200.000 dòng, tỉ lệ FP 0,5% đã là
   khoảng 1.000 cảnh báo — rule vẫn phải rất hẹp; pattern backtracking sẽ làm rule chạy quá giờ.

**Ghi chú phát hành**

```json
{"rule": {"engine": "regex", "pattern": "(?i)union\\s+select|'\\s*or\\s+1=1", "ignore_case": true},
 "technique": "T1190", "log_source": "web/WAF", "version": "2026.10.1",
 "tested": {"positives_matched": 12, "negatives_matched": 0}}
```

## Chữ ký YARA cho một họ mã độc

1. So các mẫu của họ với nhau: tìm chuỗi **chung cho mọi mẫu họ** và **không có trong mẫu sạch** — marker cấu
   hình, mutex, đường dẫn PDB, định dạng URL C2, chuỗi lỗi đặc thù.
2. **Biến thể đổi hash nhưng giữ hành vi** là chuyện thường: luật dựa hash hoặc byte ngẫu nhiên sẽ bỏ lọt một
   nửa. Dùng báo cáo phân tích mã độc để lấy đặc điểm hành vi/cấu hình bền vững.
3. **Chuỗi gần giống trong phần mềm sạch** (cùng khung `cfg=…;v=3;` nhưng khác tên) — khớp phần phân biệt.
4. Kết hợp ≥2 chuỗi độc lập; kiểm trên cả tập mẫu họ và tập sạch. Một tệp sạch bị bắt đắt như một mẫu bị sót.

## Chữ ký mạng (Suricata) và parser từ PCAP

1. Tách phiên độc trong PCAP; đối chiếu cảnh báo NSM và log DNS/HTTP/TLS.
2. Chọn đặc điểm ổn định của giao thức C2/khai thác: URI path cố định, header bất thường (User-Agent đặc thù),
   cấu trúc body, SNI/JA3 nếu có — **không** dùng IP đích làm điều kiện chính.
3. Xem thống kê alert theo rule để không viết lại một rule vốn đã nhiễu; nếu đụng rule cũ thì mở ticket tối ưu.
4. **Parser** cho log ứng dụng nội bộ: tách đúng các trường thời gian, nguồn, người dùng, hành động, kết quả để
   rule phía sau dùng được; kiểm trên mẫu log thật của hệ thống đó.
5. Với signature mạng, xác nhận engine/version, giao thức và chiều flow; replay PCAP dương/âm trong môi trường
   kiểm thử được cấp. Kiểm dữ liệu sau reassembly và giới hạn khi TLS/mất gói; so alert thực với phiên cần bắt.
   SNI/JA3/URI chỉ là đặc trưng có điều kiện, không tự chứng minh C2.
6. Với parser, chốt field/type/timezone, null/escaping và hành vi khi dòng sai; kiểm cả biến thể format, bản ghi
   thiếu trường và lỗi parse. Giữ raw record + locator để truy lại; lỗi parse không được biến thành dữ liệu sạch giả.

## Kiểm thử và phát hành có thể kiểm chứng

- Nhãn corpus đến từ bằng chứng đã review, không từ chính rule đang viết. Có mẫu âm gần giống và biến thể chưa
  dùng lúc soạn; ghi TP/FP/FN, coverage và thời gian chạy trên đúng corpus/version. Không có corpus/engine thì ghi chưa kiểm.
- Trước phát hành lưu phiên bản cũ, thay đổi, log source/field phụ thuộc, kết quả test và phạm vi áp dụng.
  Dùng quy trình review/rollout được cấp; một rule được lưu vào kho chưa có nghĩa đã bật ở engine đích.
- Sau triển khai kiểm trạng thái bật, log source, alert và tải hệ thống; kiểm cả TP quan trọng còn phát hiện.
  Nếu hồi quy, dùng phiên bản/rollback đã chuẩn bị qua quyền được cấp và bàn giao MON; không tự deploy production.

## Sai lầm thường gặp

- Bắt theo từ khoá rộng (`select`, `cmd`, `cfg=`) ⇒ FP hàng loạt.
- Luật YARA dựa hash hoặc byte ngẫu nhiên.
- Rule đúng logic nhưng không parse được trên engine đích, hoặc chạy quá giờ trên corpus lớn.
- Gán technique ATT&CK theo tên rule thay vì theo hành vi rule bắt.

Nguồn nghiệp vụ: NICE T0020, T1406 (catalog SABER).
