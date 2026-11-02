# IR · Tiếp nhận, triage, điều phối, khoanh phạm vi, theo dõi và hồ sơ sự cố

## Triage ban đầu

Triage nhanh **dựa trên thông tin ban đầu** để quyết định phản ứng khẩn cấp: loại sự cố có khả năng xảy ra, mức
độ, hành động phản ứng nhanh. Đầu ra: phân loại sự cố và báo cáo đánh giá ban đầu.

- **Chỉ dùng dữ kiện có tại t0.** Bỏ qua mọi thông tin xuất hiện sau thời điểm triage; không suy từ kết luận của
  case sau này. Đây là điểm khác giữa triage và đánh giá phạm vi đầy đủ.
- **Loại sự cố** theo danh mục trong SOP; **mức độ** tra ma trận (phạm vi × mức độ ảnh hưởng — xem
  `../../soc-mon/reference/cause-impact.md`).
- **Hành động nhanh** tương xứng với dữ kiện t0: thu ảnh bộ nhớ, cô lập máy không phải VIP, chặn IOC đã rõ, khoá
  tài khoản bị lộ, kích hoạt IRT. Chưa khoanh phạm vi thì chưa diệt trừ.

```json
{"incident_type": "ransomware", "severity": "Cao",
 "quick_actions": ["memory_dump ws-acc-07", "isolate ws-acc-07", "disable account an.nv"]}
```

## Điều phối ứng cứu sự cố

Tiếp nhận qua hotline/email/ticket → phân loại mức → **kích hoạt Incident Response Team** → chỉ định **IR Lead** →
lập **war room** (kênh liên lạc khẩn cấp). Đầu ra: Incident Ticket, IR Lead được chỉ định, war room hoạt động.

1. **Mức độ và tier xử lý** theo ma trận/SOP (sự cố chưa có hướng dẫn ⇒ Tier 3). Hai giá trị phải cùng đúng.
2. **Artifact phải thu ngay vì sắp bị ghi đè:** đọc **thời gian lưu giữ** của từng log source — nguồn có retention
   ngắn hoặc bộ đệm vòng (firewall, proxy, DNS, telemetry EDR cục bộ), RAM, kết nối mạng đang mở, danh sách tiến
   trình. Đừng bỏ sót nguồn sắp hết hạn.
3. **Mốc SLA phải tính đúng:** phản hồi = mốc tiếp nhận + 30 phút với High (15 phút với Critical); bắt đầu thu
   thập = mốc **xác nhận phạm vi** + 10 phút. Lấy mốc gốc từ vòng đời case.

```json
{"severity": "Cao", "tier": "Tier 3", "ir_lead": "…", "war_room": "…",
 "artifacts": ["ram ws-acc-07", "firewall log (giữ 24h)", "dns log (giữ 12h)"],
 "sla_marks": {"respond_by": "2026-10-17T04:51:00Z", "collect_by": "2026-10-17T05:02:00Z"}}
```

## Xác định phạm vi, mức khẩn cấp và tác động

Xác định **hệ thống nào bị tác động, tài khoản/lỗ hổng nào bị lạm dụng, dữ liệu nào có nguy cơ bị trích xuất**.
Đầu ra: scope of compromise và mức ưu tiên xử lý.

- **Host/tài khoản:** đối chiếu phiên trái phép, thực thi/persistence và detection đã kiểm chứng; detection hoặc đăng
  nhập bất thường đơn lẻ chỉ là đầu mối. Tách đã bị chiếm, bị chạm và nghi vấn, không gộp thành đã bị kiểm soát.
- **Cạnh di chuyển ngang** `{src, dst}` giữa các máy trong phạm vi.
- **Tự kiểm trước khi chốt:** với **từng** phần tử, hỏi "suy ra được từ hiện vật nào?". Không trỏ được ⇒ bỏ.

```json
{"hosts": ["ws-acc-07", "srv-file-01"], "accounts": ["an.nv"], "severity": "Cao",
 "lateral_edges": [{"src": "ws-acc-07", "dst": "srv-file-01"}], "evidence": ["…"]}
```

## Theo dõi sự cố đến khi đóng

Ticket đi từ OPEN tới CLOSE với mốc cho từng mức. SLA: **Nghiêm trọng/Cao ≤ 24 giờ, Trung bình ≤ 72 giờ**, đạt ≥ 90%.

- **Hạn của mỗi case** = mốc mở + cửa sổ SLA theo mức. **Sắp trễ** = so với thời điểm hiện tại theo ngưỡng của SOP;
  case đã quá hạn hiển nhiên thuộc nhóm này.
- **Thứ tự xử lý** các case đang mở: hạn còn lại ít nhất + mức cao trước; xếp **đủ mọi case**.
- Tính bằng luật, tất định; kiểm phép cộng thời gian (múi giờ, qua ngày, qua tháng).

```json
{"overdue_cases": ["CASE-12", "CASE-31"], "priority_order": ["CASE-31", "CASE-12", "CASE-07"]}
```

## Hồ sơ sự cố đầy đủ

Ghi tài liệu sự cố từ lúc phát hiện tới lúc xử lý xong, phục vụ cả vận hành lẫn báo cáo tháng.

- So hồ sơ với **mẫu hồ sơ sự cố** trong SOP; liệt kê đúng các mục **thực sự còn thiếu** — không đòi mục đã có,
  không đòi mục ngoài mẫu.
- Phân biệt mục **bắt buộc** với mục **nên có**: chỉ mục bắt buộc mới chặn việc đóng case.
- **Sẵn sàng phát hành báo cáo** khi không còn thiếu mục bắt buộc nào.

```json
{"missing_sections": ["root_cause", "containment_actions"],
 "required_vs_optional": {"root_cause": "required", "lessons_learned": "optional"}, "report_ready": "no"}
```

## Sai lầm thường gặp

- Triage dùng dữ kiện xuất hiện sau t0.
- Đúng mức độ nhưng sai tier xử lý.
- Tính mốc thu thập từ mốc tiếp nhận thay vì mốc xác nhận phạm vi.
- Liệt kê phạm vi không có hiện vật chống lưng.
- Đòi mục tuỳ chọn như thể bắt buộc.

Nguồn nghiệp vụ: NICE T1250, T0510, T1252, T1315, T1316 (catalog SABER).
