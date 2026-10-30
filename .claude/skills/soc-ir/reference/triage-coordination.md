# IR · Tiếp nhận, triage, điều phối, theo dõi — T0510 · T1250 · T1252 · T1315 · T1316

---

## T1250 — Phân loại ưu tiên sự cố (triage)

Triage nhanh **dựa trên thông tin ban đầu** để quyết định phản ứng khẩn cấp: loại sự cố có khả năng xảy
ra, mức độ, đề xuất hành động phản ứng nhanh. Đầu ra: xác định & phân loại sự cố, báo cáo đánh giá ban đầu.

| Subtask | Mode | Đầu vào | Phải nộp | Chấm |
|---|---|---|---|---|
| **T1250.001** | file | HV-01 tại lúc vừa nhận | `incident_type` | enum 1.0 |
| **T1250.002** | file | HV-01, HV-39 | `incident_type`, `severity` | 0.6 / 0.4 |
| **T1250.003** | soc (SIEM, SOAR) | HV-01 02 04 07 22 26 38 39 | `incident_type`, `severity`, `quick_actions[]` | 0.4 / 0.3 / 0.3 |

- **Chỉ dữ kiện có tại t0** — tuyệt đối không dùng kết luận về sau; đây là **điểm phân biệt duy nhất**
  giữa T1250 và T1252. Bỏ qua mọi bản ghi có thời điểm sau t0 (as_of), và không suy diễn từ "case đã khép".
- `incident_type` theo danh mục loại sự cố trong SOP (HV-39); `severity` tra ma trận (phạm vi × mức độ —
  xem `soc-mon/reference/cause-impact.md`).
- `quick_actions[]`: hành động phản ứng nhanh **tương xứng** với dữ kiện t0 (thu ảnh bộ nhớ, cô lập máy
  không phải VIP, chặn IOC đã rõ, khoá tài khoản bị lộ, kích hoạt IRT…). Không đề xuất diệt trừ khi chưa
  xác định phạm vi.

---

## T0510 — Điều phối các chức năng ứng cứu sự cố

Tiếp nhận sự cố qua hotline/email/ticket; phân loại mức độ; **kích hoạt Incident Response Team**; chỉ
định **IR Lead**; lập kênh liên lạc khẩn cấp (**war room**). Đầu ra: Incident Ticket, IR Lead, war room.
SLA: phản hồi **≤ 30 phút với mức High**; bắt đầu thu thập & phân tích sơ bộ **≤ 10 phút** kể từ khi
xác nhận phạm vi.

| Subtask | Mode | Đầu vào | Phải nộp | Chấm |
|---|---|---|---|---|
| **T0510.001** | file | HV-07, HV-39 | `severity`, `tier` | **[severity] × [tier]** — sai một là 0 |
| **T0510.002** | file | HV-04, HV-07, HV-39 | `severity`, `tier`, `artifacts[]` | 0.4 / 0.3 / 0.3 (recall) |
| **T0510.003** | soc (SOAR) | HV-04 07 10 38 39 | + `sla_marks` | Σ, **cap 0.5 nếu sai mốc SLA** |

- `tier`: tier xử lý theo ma trận HV-39 (vd sự cố chưa có hướng dẫn ⇒ Tier 3).
- **`artifacts[]` (.002) — thứ phải thu ngay vì sẽ bị ghi đè:** đọc **thời gian lưu giữ** của từng log
  source trong HV-04 — nguồn có retention ngắn/bộ đệm vòng (firewall, proxy, DNS, EDR telemetry cục bộ),
  bộ nhớ RAM, kết nối mạng đang mở, danh sách tiến trình. Recall ⇒ đừng bỏ sót nguồn sắp hết hạn.
- **`sla_marks` (.003)** — tính bằng luật: mốc phản hồi = mốc tiếp nhận + 30′ (High; Critical theo SLA
  dịch vụ là 15′); mốc bắt đầu thu thập = mốc **xác nhận phạm vi** + 10′. Lấy đúng mốc gốc từ HV-10;
  định dạng như input. Sai mốc ⇒ trần 0.5.

---

## T1252 — Xác định phạm vi, mức độ khẩn cấp và tác động

MON chấm mức theo ma trận; IR xác định **hệ thống nào bị tác động, tài khoản/lỗ hổng nào bị lạm dụng,
dữ liệu nào có nguy cơ bị trích xuất**; TH/CA xác định scope of compromise trên toàn hệ thống. Đầu ra:
scope of compromise và mức ưu tiên xử lý.

| Subtask | Mode | Đầu vào | Phải nộp | Chấm |
|---|---|---|---|---|
| **T1252.001** | file | HV-26 log xác thực của 1 sự cố | `affected_hosts[]` | F2 |
| **T1252.002** | file | HV-15, HV-26 | `hosts[]`, `accounts[]` | 0.5 F2 + 0.5 F2 |
| **T1252.003** | soc (SIEM, EDR, NSM) | HV-14 15 18 22 26 33 37 38 39 | `hosts[]`, `accounts[]`, `severity`, `lateral_edges[]` `{src,dst}` | 0.25 / 0.25 / 0.3 / 0.2 |

- Host bị ảnh hưởng: đích của đăng nhập thành công bằng tài khoản bị chiếm, máy có tiến trình/persistence
  độc (HV-15), máy có detection EDR (HV-14). Account: tài khoản bị dùng bất thường. F2 ⇒ ưu tiên đủ.
- **.003 — tự kiểm trước khi chốt:** với **mỗi** phần tử, hỏi "phần tử này suy ra được từ hiện vật đã
  cấp không, bằng bản ghi nào?". Không trỏ được ⇒ bỏ. Đây là chỗ khác biệt giữa điều tra và đoán.

---

## T1315 — Theo dõi sự cố từ khi phát hiện đến khi xử lý xong

Ticket chuyển OPEN → CLOSE với mốc thời gian cho từng mức. SLA: **Nghiêm trọng và Cao ≤ 24 giờ, Trung
bình ≤ 72 giờ**, đạt ≥ 90%.

| Subtask | Mode | Đầu vào | Phải nộp | Chấm |
|---|---|---|---|---|
| **T1315.001** | file | HV-10 K case đang mở + bảng SLA | `overdue_cases[]` (sắp trễ hạn) | F1 |
| **T1315.002** | file | HV-10, HV-39 | `priority_order[]` (K = 15 case), `overdue_cases[]` | 0.6 thứ tự + 0.4 F1 |
| **T1315.003** | soc (SOAR) | HV-02 06 07 08 09 10 13 39 | `priority_order[]`, `overdue_cases[]`, `sla_constraint` | (0.6·ρ + 0.4·F1) × **[SLA]** |

- **Hạn từng case** = mốc mở (theo HV-10) + cửa sổ SLA của severity. **Sắp trễ** = so với mốc "hiện
  tại" của đề (as_of) và ngưỡng mà input/SOP định nghĩa; case đã quá hạn hiển nhiên thuộc nhóm này.
- **Thứ tự xử lý:** hạn còn lại ít nhất + severity cao trước; liệt kê **đủ 15 case**, đúng ID case.
- **.003:** deadline và tập trễ hạn do verifier **tự tính bằng luật** từ severity + timestamp — không cần
  người gán nhãn ⇒ làm tất định như máy, kiểm lại phép cộng thời gian (múi giờ, ngày đổi tháng).

---

## T1316 — Ghi nhận sự cố từ khi phát hiện đến khi xử lý xong

Ghi tài liệu sự cố phục vụ cả vận hành lẫn báo cáo tháng. Đầu ra: hồ sơ sự cố đầy đủ trên hệ thống SOC.

| Subtask | Mode | Đầu vào | Phải nộp | Chấm |
|---|---|---|---|---|
| **T1316.001** | file | HV-07 bị xoá M mục | `missing_sections[]` | set_delta |
| **T1316.002** | file | HV-07, HV-08, HV-09 | `missing_sections[]`, `required_vs_optional{}` | 0.7 / 0.3 |
| **T1316.003** | soc (SOAR) | HV-07 08 09 10 13 32 36 39 | + `report_ready` | Σ − **0.1 × số mục đòi thừa** |

- So hồ sơ với **mẫu hồ sơ sự cố** trong SOP (HV-39): liệt kê đúng các mục **thực sự vắng**. Đòi một mục
  đã có, hoặc đòi mục không thuộc mẫu ⇒ "đòi thừa" (set_delta ở .001, −0.1/mục ở .003).
- **`required_vs_optional{}`:** phân biệt mục **bắt buộc** với mục **nên có** — **chỉ mục bắt buộc mới
  chặn việc đóng case**.
- **`report_ready` (.003):** sẵn sàng phát hành báo cáo chỉ khi **không thiếu mục bắt buộc nào**.
- .003 là bài **tự sinh nhãn**: script lấy bản đầy đủ, xoá ngẫu nhiên M mục, ghi lại danh sách đã xoá —
  vô hạn mẫu, nhãn tất định.

## Bẫy hay gặp

- Triage dùng dữ kiện sau t0.
- `severity` đúng mà `tier` sai ở T0510.001 ⇒ 0.
- Tính mốc thu thập từ mốc tiếp nhận thay vì mốc **xác nhận phạm vi**.
- Liệt kê phạm vi không có hiện vật chống lưng.
- Đòi thừa mục tuỳ chọn như thể bắt buộc.
