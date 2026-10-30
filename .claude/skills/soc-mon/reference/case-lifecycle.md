# MON · Vòng đời case: ticket, leo thang, thông báo, hàng đợi, báo cáo

Nhóm việc này là **tuân thủ quy trình**: câu trả lời đúng gần như luôn tra được từ SOP, ma trận severity,
bảng RASCI, bảng SLA và danh mục tài sản của khách hàng. Làm như kế toán — tra bảng, tính chính xác, cùng
đầu vào thì cùng kết quả. Không diễn giải, không phỏng đoán.

## Ghi nhận sự cố (ticket)

Mỗi sự cố là **một ticket**, ghi đầy đủ từ lúc phát hiện, trạng thái **OPEN → CLOSE**. Sự cố **đã có hướng
dẫn** gán cho khách hàng/đội theo SOP; sự cố **chưa có hướng dẫn** gán cho **Tier 3**. Mục tiêu đúng hạn ≥ 90%.

**Khi mở hoặc rà một ticket**
1. Đối chiếu với **danh sách trường bắt buộc** của SOP; ticket thiếu trường bắt buộc thì bổ sung trước khi
   chuyển tiếp. Phân biệt trường bắt buộc với trường tuỳ chọn.
2. `incident_type` theo danh mục loại sự cố trong SOP; `severity` tra ma trận (xem `cause-impact.md`).
3. `entities`: các thực thể liên quan dạng cặp (loại, giá trị) — host, tài khoản, IP, hash, URL.
4. `assigned_team`: có playbook ⇒ đội/khách hàng theo SOP; chưa có hướng dẫn ⇒ Tier 3.

```json
{"case_id": "CASE-…", "status": "OPEN", "incident_type": "…", "severity": "Cao",
 "entities": [["host", "ws-acc-07"], ["account", "an.nv"]], "assigned_team": "Tier 3",
 "missing_fields": []}
```

## Leo thang

Leo thang những sự cố có thể gây **tác động tức thời và kéo dài**. Sự cố chưa có hướng dẫn được chuyển
thành case gán **Tier 3**, có người chịu trách nhiệm. Hạn leo thang: **Nghiêm trọng/Cao ≤ 24 giờ, Trung bình
≤ 72 giờ**.

| Quyết định | Khi nào |
|---|---|
| **Leo thang** | chưa có playbook cho loại sự cố · tác động đang diễn ra (C2 còn sống, lan sang máy khác, dữ liệu đang ra) · vượt thẩm quyền Tier 1/2 · SOP bắt buộc theo mức độ |
| **Tự khép** | FP đã chứng minh · hoặc sự cố có hướng dẫn và đã xử lý xong theo playbook |

- **Tier đích** theo ma trận — không phải lúc nào cũng là tier cao nhất.
- **Hạn leo thang** = mốc bắt đầu tính SLA (đọc trong vòng đời case: mốc tạo cảnh báo hay mốc xác nhận sự cố)
  + cửa sổ SLA của mức độ. Tính chính xác tới phút.
- Leo thang thừa và leo thang thiếu đều là lỗi — ghi lý do quyết định vào worklog.

```json
{"decision": "escalate", "target_tier": "Tier 3", "escalate_deadline": "2026-10-18T04:21:00Z",
 "reason": "chưa có hướng dẫn; kết nối C2 còn hoạt động"}
```

## Thông báo đúng người, đúng kênh, đúng hạn

Thông báo cảnh báo/sự cố tới khách hàng, đầu mối kỹ thuật, quản lý được chỉ định, đội IR và nhân sự nhà cung
cấp dịch vụ theo mô hình **RASCI** (Responsible, Accountable, Support, Consulted, Informed) đã phân giữa Bên A
và Bên B.

1. Lấy **mức sự cố** và **tài sản bị ảnh hưởng** (danh mục tài sản → chủ sở hữu, đơn vị, **thuộc khách hàng
   nào**).
2. Tra **RASCI** theo mức ⇒ các vai phải báo ⇒ liên hệ cụ thể. Không thêm người "cho chắc".
3. Tra **kênh bắt buộc** theo mức (hotline/điện thoại, email, ticket/SOAR…).
4. **Hạn thông báo** = mốc phát hiện/xác nhận + cửa sổ SLA của mức.
5. **Không báo nhầm khách hàng:** bằng chứng có thể lẫn tài sản của khách hàng khác — chỉ báo đầu mối của khách
   sở hữu tài sản bị ảnh hưởng. Lộ thông tin sự cố sang khách khác là một sự cố bảo mật.
6. Bước này phải **tất định**: cùng case thì cùng danh sách, cùng kênh, cùng hạn — mọi lần.

```json
{"recipients": ["soc-lead@khach-a.vn", "it-owner@khach-a.vn"], "channel": "hotline",
 "notify_deadline": "2026-10-17T04:51:00Z", "no_cross_customer": "verified"}
```

## Giám sát liên tục và hàng đợi ca trực

- **Sức khoẻ nguồn log:** nắm nhịp ghi bình thường của từng nguồn; khoảng trống bất thường là **mất log** cần
  báo — đối chiếu danh mục log source để phân biệt mất log với không có hoạt động. Ghi `log_gap` (mốc bắt đầu
  và độ dài khoảng mất).
- **Xếp hàng đợi** cảnh báo trong ca: (1) mức Nghiêm trọng > Cao > Trung bình > Thấp; (2) hạn SLA còn lại ít nhất
  trước; (3) độ quan trọng tài sản (VIP, cấp 3, core). **Mọi cảnh báo Nghiêm trọng/Cao phải được xử lý trong 30
  phút** — kiểm lại hàng đợi đảm bảo điều đó.

```json
{"queue_order": ["ALERT-3", "ALERT-1", "ALERT-7"], "log_gap": {"start": "2026-10-17T02:10:00Z", "minutes": 35},
 "sla_constraint": "all critical/high within 30m"}
```

## Báo cáo vận hành định kỳ (báo cáo dịch vụ tháng)

Tổng quan alert và rule theo mẫu báo cáo dịch vụ tháng. Mọi con số tính lại được từ dữ liệu thô — đếm chính
xác, không làm tròn.

| Chỉ số | Cách tính |
|---|---|
| `total_alerts` | tổng số cảnh báo trong kỳ |
| `true_positives` / `false_positives` | số cảnh báo theo phán quyết TP / FP |
| `critical_high` | số cảnh báo mức critical **hoặc** high |
| `distinct_rules` | số rule khác nhau đã sinh cảnh báo |
| `% xử lý đúng hạn` | case xử lý trong hạn SLA theo mức / tổng case |
| `noisy_rules` | top-5 rule nhiễu nhất (nhiều FP nhất) — gửi Content Security tối ưu |

```json
{"metrics": {"total_alerts": 1284, "true_positives": 37, "false_positives": 1247, "critical_high": 92,
             "distinct_rules": 41, "on_time_pct": 93.5},
 "noisy_rules": ["RULE_017", "RULE_004", "RULE_022", "RULE_031", "RULE_009"]}
```

## Sai lầm thường gặp

- Báo thừa người nhận, sai kênh hoặc sai hạn.
- Báo sang đầu mối của khách hàng khác.
- Leo thang mọi thứ, hoặc tự khép sự cố chưa có hướng dẫn.
- Tính hạn SLA từ sai mốc gốc.
- Để một cảnh báo Cao nằm sau mốc 30 phút trong hàng đợi.

Nguồn nghiệp vụ: NICE T1241, T1242, T1349, T1428, T1350, T1290 (catalog SABER).
