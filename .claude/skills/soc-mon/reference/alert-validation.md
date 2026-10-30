# MON · Kiểm chứng cảnh báo — T1112 (cảnh báo mạng) · T1387 (cảnh báo IDS)

Kiểm chứng là **bước đầu tiên và có KPI riêng** của dịch vụ: SLA tính từ lúc cảnh báo sinh ra tới khi
gán vào Case hoặc đóng FP. Đầu ra nghiệp vụ: cảnh báo được gán vào một Case (HV-07) hoặc chuyển
trạng thái False Positive.

## Quy trình kiểm chứng (dùng cho cả T1112 và T1387)

1. **Đọc claim của cảnh báo**, không đọc tên rule: cảnh báo đang khẳng định điều gì đã xảy ra
   (vd "interpreter do tài liệu Office sinh ra rồi beacon ra ngoài")?
2. **Tìm bằng chứng xác nhận/bác bỏ claim** trong log thô (HV-02), telemetry tiến trình (HV-15),
   netconn (HV-17), PCAP (HV-24): sự kiện cha–con, kết nối ra, payload.
3. **Đối chiếu ngữ cảnh hợp lệ** — từng dấu hiệu dưới đây kéo về FP:
   change ticket có hiệu lực · nguồn trong admin subnet · file có chữ ký của nhà cung cấp tin cậy ·
   công cụ quản trị phổ biến trong tổ chức (org_prevalence = common) · nằm trong HV-40 whitelist ·
   đúng khung giờ thay đổi đã phê duyệt.
4. **Xác định rule nào bắn và trên tài sản nào** từ chính bản ghi log (không suy từ tên cảnh báo).
5. **Kết luận** — và nếu bằng chứng không đủ để xác nhận hay bác bỏ, chọn giá trị không kết luận.

---

## T1112 — Kiểm chứng cảnh báo mạng

| Subtask | Mode | Đầu vào | Phải nộp | Chấm |
|---|---|---|---|---|
| **T1112.001** | file | HV-01 | `verdict` ∈ {`TP`,`FP`} | enum, 1.0 |
| **T1112.002** | file | HV-01, HV-02 (±60′) | `verdict`, `triggering_rule`, `affected_asset` | 0.5 / 0.25 / 0.25 |
| **T1112.003** | soc (SIEM, EDR) | HV-01 02 04 12 15 38 | xem dưới | Σwᵢsᵢ, **cap 0.30 nếu classification sai**, gate CITE |

**T1112.001** — một cảnh báo kèm file bị cảnh báo. Đọc `alerted_file` (path, sha256, signed, signer,
org_prevalence, heuristic_family) và `features`. Dấu hiệu FP điển hình trong exemplar: công cụ remote
execution do IT chạy trong change window, file ký bởi `trusted-it-vendor`, nguồn trong admin subnet,
`change_ticket_present: true`. Heuristic family chung chung (`TestLoader`, `PUA`) không đủ để kết TP.

**T1112.002** — thêm log thô ±60 phút. `triggering_rule` = tên rule thực sự khớp trong log (chép
nguyên văn), `affected_asset` = host thực sự bị tác động (chuẩn hoá theo tên host trong log). Hai
trường này là *suy ra từ log*, sai một trường mất 0.25 dù verdict đúng.

**T1112.003** — trọn case SIEM, xác thực **claim** của cảnh báo. Đã có hồ sơ mẫu `T1112_0001`.

| Field | Giá trị | Trọng số | Nghĩa |
|---|---|---|---|
| `classification` | `TRUE_POSITIVE` / `FALSE_POSITIVE` / `INCONCLUSIVE` | 0.30 | kết luận tổng thể về sự cố |
| `claim_confirmed` | `confirmed` / `refuted` / `unverified` | 0.30 | bằng chứng xác nhận, bác bỏ, hay không đủ để kiểm claim |
| `alert_claim` | `valid` / `invalid` | 0.15 | claim của cảnh báo có đúng với thực tế không |
| `triggering_rule` | chuỗi | 0.125 | rule thực sự bắn |
| `affected_asset` | chuỗi | 0.125 | tài sản thực sự bị tác động |
| `explain` | list evidence ID | gate | ≥1 ID hợp lệ, 0 ID bịa |

Nhất quán bắt buộc: TP ⇒ `confirmed` + `valid`; FP ⇒ `refuted` + `invalid`; không đủ dữ liệu ⇒
`INCONCLUSIVE` + `unverified`. **Sai `classification` thì trần điểm 0.30** — chốt nó trước. `explain`
trích các ID như `LOG-…`, `PROC-…` thực sự chứng minh (vd sự kiện `winword.exe` sinh interpreter với
tham số encode + kết nối ra host hiếm). Lưu ý: tập nhãn của classification/claim_confirmed/alert_claim
đang là lựa chọn DEV, còn chờ chủ nguồn duyệt (xem notes trong module `t1112_003`).

---

## T1387 — Thẩm định cảnh báo IDS

Kiểm chứng cảnh báo từ IDS/IPS và sensor khác **trong phạm vi nguồn log đã on-board theo hợp đồng**
(HV-04). Kết luận cảnh báo đúng hay sai.

| Subtask | Mode | Đầu vào | Phải nộp | Chấm |
|---|---|---|---|---|
| **T1387.001** | file | HV-21, HV-24 (PCAP chính phiên đó) | `verdict` | enum, 1.0 |
| **T1387.002** | file | HV-21, HV-24 | `verdict`, `payload_offset` | 0.6 / 0.4 (IoU ≥ 0.8) |
| **T1387.003** | soc (NSM/IDS, SIEM) | HV-02 21 22 23 24 27 37 38 39 | `verdict`, `payload_offset`, `real_src_ip`, `real_severity` | 0.4 / 0.25 / 0.2 / 0.15 |

**Quy trình đọc PCAP cho cảnh báo IDS**
1. Tách đúng phiên (5-tuple, thời điểm) mà cảnh báo trỏ tới.
2. Tái dựng payload tầng ứng dụng (HTTP body/URI, DNS query…) và tìm đoạn byte khớp chữ ký.
3. TP khi payload thật sự mang nội dung độc hại mà chữ ký mô tả; FP khi chữ ký khớp nhầm (chuỗi giống
   nhưng ngữ cảnh lành tính, vd nội dung tài liệu, ô tìm kiếm) hoặc phiên không chứa payload đó.

**T1387.002 — `payload_offset`**: khoảng byte `{"start": a, "end": b}` (hoặc `[a, b]`) trong payload
làm chữ ký khớp; chấm bằng **IoU ≥ 0.8** với khoảng đúng ⇒ chỉ khoanh đúng đoạn khớp, không khoanh cả
gói. Dùng cùng gốc offset với đề (đầu payload ứng dụng hay đầu gói — đọc mô tả trong input).

**T1387.003 — có NAT trong sơ đồ mạng (HV-37)**
- `real_src_ip`: IP nguồn **thật**, truy ngược qua bảng NAT/log firewall (HV-27) và flow (HV-22) —
  không phải IP sau NAT mà IDS nhìn thấy.
- `real_severity`: chấm lại theo **vai trò máy đích** trong HV-38 và ma trận HV-39 (máy chủ core / hệ
  thống cấp 3 / máy VIP nặng hơn máy trạm thường), không chép severity gốc của IDS.

## Bẫy hay gặp

- Kết TP chỉ vì tên rule nghe nguy hiểm, hoặc FP chỉ vì file có chữ ký — chữ ký và whitelist là bằng
  chứng mạnh nhưng phải đi cùng ngữ cảnh (change ticket, admin subnet, khung giờ).
- Chép `triggering_rule` từ tên cảnh báo thay vì từ dòng log thực sự khớp.
- Báo IP sau NAT là nguồn tấn công.
- Ở `.003`, trích một ID không có trong input ⇒ trượt gate CITE ⇒ 0 toàn bài.
