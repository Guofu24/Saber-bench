# MON · Vòng đời case — ghi ticket, leo thang, thông báo, giám sát liên tục, báo cáo

T1241 ghi nhận · T1242 leo thang · T1349 truyền đạt cảnh báo · T1428 thông báo đầu mối · T1350 giám sát
liên tục · T1290 báo cáo định kỳ. Đây là nhóm bài **tuân thủ quy trình**: đáp án gần như tính được bằng
luật từ HV-07 (case), HV-10 (vòng đời & SLA), HV-38 (tài sản), HV-39 (ma trận severity, SOP, RASCI,
kênh, SLA). Làm như kế toán: tra bảng, tính đúng tuyệt đối, không phỏng đoán.

---

## T1241 — Ghi nhận các sự cố an ninh mạng (ticket)

Mỗi sự cố = **một ticket** trên hệ thống SOC, ghi đầy đủ từ lúc phát hiện, trạng thái OPEN → CLOSE.
Sự cố **đã có hướng dẫn** gán cho khách hàng; sự cố **chưa có hướng dẫn** gán cho **Tier 3**. SLA: hoàn
thành đúng hạn ≥ 90%.

| Subtask | Mode | Đầu vào | Phải nộp | Chấm |
|---|---|---|---|---|
| **T1241.001** | file | HV-07 bị xoá M trường | `missing_fields[]` | set_delta |
| **T1241.002** | file | HV-07 (đã xoá kết luận), HV-39 | `incident_type`, `severity` | 0.5 / 0.5 |
| **T1241.003** | soc (SOAR, SIEM) | HV-01 02 04 07 08 38 39 | `incident_type`, `severity`, `entities[]`, `assigned_team` | 0.3 / 0.2 / 0.3 / 0.2 |

- **.001:** so hồ sơ với danh sách **trường bắt buộc** của ticket (SOP trong HV-39 hoặc schema HV-07);
  chỉ liệt kê trường bắt buộc thực sự thiếu — liệt kê thừa trường tuỳ chọn bị trừ (set_delta).
- **.002:** `incident_type` theo danh mục loại sự cố của SOP; `severity` tra ma trận HV-39 (xem
  `cause-impact.md`).
- **.003:** `entities[]` là tập cặp hai thành phần (kiểu `tuple` ⇒ dict `{a, b}` hoặc `[x, y]` —
  thường là loại thực thể và giá trị: host, tài khoản, IP, hash…; dùng đúng dạng input mô tả).
  `assigned_team`: **1/3 số case thuộc loại chưa có hướng dẫn ⇒ nhãn là Tier 3**; case có playbook ⇒
  đội/khách hàng theo SOP.

---

## T1242 — Leo thang sự cố có thể gây tác động tức thời và kéo dài

Sự cố chưa có hướng dẫn được chuyển thành case và gán **Tier 3** của VCS. Đầu ra: case Tier 3 có người
chịu trách nhiệm. SLA leo thang: **Nghiêm trọng/Cao ≤ 24 giờ, Trung bình ≤ 72 giờ**.

| Subtask | Mode | Đầu vào | Phải nộp | Chấm |
|---|---|---|---|---|
| **T1242.001** | file | HV-07 cắt tại mốc Tier 1 kết thúc | `decision` (leo thang / tự khép) | enum 1.0 |
| **T1242.002** | file | HV-07, HV-39 | `decision`, `target_tier` | 0.6 / 0.4 |
| **T1242.003** | soc (SOAR, SIEM, EDR, NSM) | HV-05 07 08 10 17 22 39 | `decision`, `target_tier`, `escalate_deadline` | 0.5 / 0.3 / 0.2 (±0′) |

**Luật quyết định leo thang**
- **Leo thang** khi: không có playbook/hướng dẫn cho loại sự cố; tác động **đang diễn ra hoặc tức thời**
  (kết nối C2 còn sống HV-17/HV-22, lan sang máy khác, dữ liệu đang ra); vượt thẩm quyền Tier 1 theo
  HV-39; hoặc severity buộc leo thang theo SOP.
- **Tự khép** khi: FP đã chứng minh; hoặc sự cố có hướng dẫn và Tier 1 đã xử lý xong theo playbook.
- `target_tier`: tier đích đúng theo ma trận HV-39 — không phải lúc nào cũng là cao nhất.
- `escalate_deadline` (.003): mốc **tính chính xác** = mốc bắt đầu tính SLA (theo HV-10) + cửa sổ SLA của
  severity; đơn vị và định dạng như input; dung sai **±0**. Đề trộn 50/50 case leo thang và case tự
  khép, và báo riêng under-/over-escalation — cả hai chiều đều là lỗi.

---

## T1349 — Truyền đạt cảnh báo tấn công/xâm nhập · T1428 — Thông báo đầu mối

Thông báo tới khách hàng/đầu mối kỹ thuật/quản lý được chỉ định qua **kênh đã thống nhất**, theo mô
hình **RASCI** (Responsible, Accountable, Support, Consulted, Informed) phân giữa Bên A và Bên B.

| Subtask | Mode | Đầu vào | Phải nộp | Chấm |
|---|---|---|---|---|
| **T1349.001** | file | HV-07, HV-39 | `recipients[]` | F1 |
| **T1349.002** | file | + HV-10 | `recipients[]`, `channel`, `deadline` | F1 × [channel] × [deadline] |
| **T1349.003** | soc (SOAR) | HV-01 02 07 08 10 15 32 36 38 39 | + `no_cross_customer` | F1 × [channel] × [deadline] × **[không báo nhầm khách khác]** |
| **T1428.001** | file | HV-07, HV-39 | `notify_deadline` | số ±0′ |
| **T1428.002** | file | HV-07, HV-38, HV-39 | `recipients[]`, `notify_deadline` | F1 × [deadline] |
| **T1428.003** | soc (SOAR) | HV-07 08 10 38 39 | `recipients[]`, `channel`, `notify_deadline` | F1 × [channel] × [deadline]; **chạy lặp 5 lần đo độ ổn định** |

**Quy trình**
1. Lấy **mức sự cố** (đã chấm theo HV-39) và **tài sản bị ảnh hưởng** (HV-38 → chủ sở hữu, đơn vị).
2. Tra bảng RASCI cho mức đó ⇒ tập vai phải báo ⇒ ánh xạ vai → **liên hệ cụ thể** (email chuẩn hoá chữ
   thường). Không thêm người "cho chắc" (F1 trừ báo thừa).
3. Tra **kênh** bắt buộc cho mức đó (điện thoại/hotline, email, ticket/SOAR…) — sai kênh ⇒ ×0.
4. Tính **hạn thông báo** = mốc phát hiện/xác nhận + cửa sổ SLA của mức; sai mốc ⇒ ×0.
5. **T1349.003 — chống báo nhầm khách hàng:** bằng chứng cố ý lẫn tài sản của **khách hàng khác**. Kiểm
   từng tài sản trong HV-38 thuộc khách nào; chỉ báo đầu mối của khách sở hữu tài sản bị ảnh hưởng.
   Lộ thông tin sự cố sang khách khác = 0 điểm (và là sự cố bảo mật thật ngoài đời).
6. **T1428.003** là bài tuân thủ thuần tuý, chạy lặp 5 lần: cùng đề phải ra **cùng đáp án** — làm bằng
   tra bảng tất định, không diễn giải.

---

## T1350 — Giám sát liên tục hoạt động hệ thống

Giám sát **24×7×365, kể cả ngày lễ** — cam kết nền của dịch vụ.

| Subtask | Mode | Đầu vào | Phải nộp | Chấm |
|---|---|---|---|---|
| **T1350.001** | file | HV-02 log liên tục có 1 khoảng mất | `log_gap` | số ±5′ |
| **T1350.002** | file | HV-01 (luồng cảnh báo ca 8 giờ), HV-02 | `queue_order[]`, `log_gap` | 0.6·ρ + 0.4·[log_gap] |
| **T1350.003** | soc (SIEM, SOAR) | HV-01 02 04 05 06 38 39 | `queue_order[]`, `log_gap`, `sla_constraint` | 0.6·ρ·**[SLA]** + 0.4·[log_gap] |

- **Khoảng mất log:** tính nhịp ghi bình thường của nguồn (khoảng cách điển hình giữa các sự kiện), tìm
  khoảng trống bất thường lớn nhất; báo `log_gap` theo đúng định nghĩa input yêu cầu (mốc bắt đầu hoặc
  độ dài), dung sai ±5 phút. Đối chiếu HV-04 (sức khoẻ log source) để phân biệt *mất log* với *không có
  hoạt động*.
- **Xếp hàng đợi ca trực:** sắp theo (1) severity Nghiêm trọng > Cao > Trung bình > Thấp, (2) hạn SLA còn
  lại (hạn sớm xử lý trước), (3) độ quan trọng tài sản (VIP, cấp 3, core). Liệt kê **đủ mọi cảnh báo**.
- **.003 — gate SLA:** mọi case Nghiêm trọng/Cao phải nằm trong nhóm được xử lý **≤ 30 phút**. Một case
  Cao xếp muộn hơn mốc 30′ ⇒ phần xếp hàng nhân 0.

---

## T1290 — Báo cáo sự kiện và hoạt động mạng định kỳ (báo cáo dịch vụ tháng)

| Subtask | Mode | Đầu vào | Phải nộp | Chấm |
|---|---|---|---|---|
| **T1290.001** | file | HV-06 CSV alert 30 ngày | `metrics{}` 5 con số | mỗi ô ±0, điểm = số ô đúng / 5 |
| **T1290.002** | file | HV-06, HV-07 | `metrics{}`, `noisy_rules[]` (top-5) | 0.6 (±0.5pp) / 0.4 |
| **T1290.003** | soc (SIEM, SOAR) | HV-01 04 06 07 10 35 | `metrics{}`, `noisy_rules[]` | 0.7 / 0.3 — verifier tự tính lại toàn bộ |

- **.001 — năm khoá của exemplar:** `total_alerts` (tổng dòng), `true_positives` (verdict TP),
  `false_positives` (verdict FP), `critical_high` (severity critical **hoặc** high), `distinct_rules`
  (số rule khác nhau). Đếm chính xác trên toàn bộ dòng, đúng tên khoá; không làm tròn.
- **.002/.003:** thêm `% xử lý đúng hạn` (so mốc xử lý thực tế trong HV-07/HV-10 với hạn SLA theo
  severity; dung sai ±0.5 điểm phần trăm) và **top-5 rule nhiễu** = rule có nhiều FP nhất (hoặc tỉ lệ FP
  cao nhất theo định nghĩa trong đề) — đúng 5 tên rule.
- Dùng đúng tên khoá metric mà input/đề nêu; khoá lạ không được chấm.

## Bẫy hay gặp

- Báo thừa người nhận "cho chắc" (F1 trừ), sai kênh hoặc sai hạn (×0).
- Báo sang đầu mối của khách hàng khác.
- Leo thang mọi thứ (over-escalation) hoặc tự khép sự cố chưa có hướng dẫn (under-escalation).
- Tính hạn SLA từ sai mốc gốc (mốc tạo cảnh báo vs mốc xác nhận sự cố) — đọc HV-10 xem mốc nào.
