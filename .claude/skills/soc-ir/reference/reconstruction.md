# IR · Tái dựng — T0173 (dòng thời gian) · T1391 (tái dựng tấn công, Patient Zero)

---

## T0173 — Phân tích dòng thời gian (timeline)

Tái dựng dòng thời gian sự cố **từ lúc bắt đầu xâm nhập tới khi bị phát hiện**, đối chiếu log đa nguồn:
SIEM, EDR, Firewall, hệ thống xác thực, Cloud. Đầu ra: timeline chi tiết trình tự hành vi của attacker.

| Subtask | Mode | Đầu vào | Phải nộp | Chấm |
|---|---|---|---|---|
| **T0173.001** | file | HV-02 (30 sự kiện ở **3 múi giờ**) | `event_order[]` | Kendall τ |
| **T0173.002** | file | HV-02, HV-26 | `event_order[]`, `utc_times[]` | 0.6 (τ × recall) + 0.4 (±5′) |
| **T0173.003** | soc (SIEM, EDR) | HV-02 15 16 18 26 27 28 | `event_order[]`, `milestones[]` | 0.5 + 0.5 recall — **6 mốc bắt buộc, lệch > ±5′ tính sai** |

**Chuẩn hoá thời gian — làm trước mọi thứ**
1. Mỗi sự kiện có **giờ địa phương + offset UTC** (exemplar: `+07:00`, `+00:00`, `-05:00`). UTC = giờ địa
   phương **trừ** offset (vd `10:00+07:00` = `03:00Z`).
2. Nguồn không ghi offset: lấy múi giờ của **nguồn** (cấu hình log source trong HV-04/mô tả input); không
   đoán theo vị trí máy.
3. Lưu ý lệch đồng hồ giữa nguồn nếu đề mô tả clock skew.
4. **Hard negative (gold T0173.002):** hai sự kiện ở hai múi giờ mà giờ địa phương trông theo một thứ tự
   nhưng thứ tự UTC thật **ngược lại**. Không bao giờ sắp theo chuỗi giờ địa phương.

**Định dạng (gold T0173.002):** `{"event_order": ["evt-..", ...], "utc_times": ["YYYY-MM-DDTHH:MM:SSZ", ...]}`
— `utc_times` **thẳng hàng với `event_order`**. Liệt kê **đủ mọi ID** (recall nhân vào điểm thứ tự).

**.003 — 6 mốc bắt buộc:** initial access · leo thang đặc quyền · lateral movement · persistence ·
exfiltration · phát hiện. Với mỗi mốc, chọn sự kiện **sớm nhất có bằng chứng** cho giai đoạn đó, ghi thời
điểm UTC; lệch quá ±5 phút là sai. Mốc "phát hiện" là lúc hệ thống/analyst phát hiện (cảnh báo đầu tiên),
không phải lúc attacker hành động.

---

## T1391 — Tái dựng các cuộc tấn công độc hại

Tái dựng chuỗi tấn công: xác định **Patient Zero** và điểm xâm nhập đầu tiên, vẽ **bản đồ lây nhiễm
(Infection Topology)** thể hiện lộ trình lateral movement, liệt kê máy và tài khoản bị chiếm quyền. Đầu
ra: Attack Path & Lateral Movement Map, danh sách hệ thống và tài khoản bị ảnh hưởng.

| Subtask | Mode | Đầu vào | Phải nộp | Chấm |
|---|---|---|---|---|
| **T1391.001** | file | HV-26 log xác thực nhiều máy | `patient_zero` | enum 1.0 |
| **T1391.002** | file | HV-15, HV-26 | `patient_zero`, `infection_edges[]` `{src, dst, account}` | 0.5 / 0.5 |
| **T1391.003** | soc (SIEM, EDR, NSM) | HV-12 15 22 26 28 32 36 | `patient_zero`, `infection_edges[]` `{src, dst, account, logon_type}`, `timeline[]` | 0.35 / 0.35 / 0.3, **cap 0.5 nếu sai Patient Zero** |

**Xác định Patient Zero**
1. Patient Zero = máy **đầu tiên bị attacker kiểm soát** — nơi có **điểm vào** (khai thác dịch vụ phơi ra
   ngoài HV-28, thực thi từ email/tài liệu HV-15, đăng nhập đầu tiên bằng thông tin bị lộ), và từ đó các
   cạnh lây nhiễm toả ra.
2. Đi ngược đồ thị lateral: máy nào là **nguồn** của các cạnh mà **không là đích** của cạnh độc nào trước
   nó? Đó là ứng viên gốc.
3. **Bẫy .003:** đề cấy **1 máy có dấu vết sớm hơn nhưng do quét lỗ hổng hợp lệ** (HV-12 ticket/lịch quét,
   scanner trong whitelist). Timestamp sớm nhất **không** phải tiêu chí — tiêu chí là hoạt động độc hại
   đầu tiên có chuỗi nhân quả nối tới phần còn lại. Sai Patient Zero ⇒ trần 0.5.

**Bản đồ lây nhiễm**
- Cạnh = attacker đi từ `src` sang `dst` bằng `account` (và `logon_type` ở .003: 3 network, 10 RDP, …).
- Chỉ cạnh **độc** (đăng nhập bằng tài khoản bị chiếm, ngoài jump host/PAM, kèm thực thi từ xa); không đưa
  phiên quản trị hợp lệ.
- Host chuẩn hoá tên ngắn, account bỏ domain; hướng cạnh theo chiều di chuyển của attacker.
- `timeline[]` (.003): thứ tự sự kiện của chuỗi (thứ tự + recall mốc), thời gian chuẩn UTC như T0173.

## Bẫy hay gặp

- Sắp theo giờ địa phương; quên rằng `+07:00` phải trừ 7 giờ để ra UTC.
- `utc_times` không thẳng hàng với `event_order`.
- Chọn Patient Zero theo timestamp sớm nhất (dính bẫy scanner hợp lệ).
- Đảo hướng cạnh, thêm cạnh quản trị hợp lệ, thiếu `logon_type` ở .003.
