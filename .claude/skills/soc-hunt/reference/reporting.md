# HUNT · Technical Report — T1104 (ghi nhận những gì đã biết về vụ xâm nhập)

Ghi lại **toàn bộ những gì đã xác định được** về cuộc xâm nhập. IR lập Báo cáo kỹ thuật chi tiết
(timeline, root cause, scope of compromise, mapping kỹ thuật); Threat Hunting và Compromise Assessment
lập **Technical Report kèm đầy đủ bằng chứng số**. SLA: báo cáo sơ bộ ≤ 24h; chính thức ≤ 24h sau khi
xong phân tích **và peer review**.

| Subtask | Mode | Đầu vào | Phải nộp | Chấm |
|---|---|---|---|---|
| **T1104.001** | file | HV-36 gói bằng chứng | 6 trường bắt buộc của Technical Report | mỗi trường 1/6 (số trường đúng / 6) |
| **T1104.002** | file | HV-18, HV-36 | `fields{}` + `citations[]` | 0.8 / 0.2 — mỗi trường kèm trích dẫn `{hiện vật, định vị, trích}` |
| **T1104.003** | file | HV-02 05 16 18 26 27 32 33 36 38 | Technical Report đầy đủ theo **schema HV-33** | xem dưới |

**Schema Technical Report (T1104.003 — không ô nào cần người đọc)**

| Field | Kiểu chấm | Trọng số | Nội dung |
|---|---|---|---|
| `scope[]` | F2 (host) | 0.15 | máy/tài khoản bị xâm phạm |
| `timeline[]` | thứ tự + recall mốc | 0.20 | các mốc theo thời gian thật (UTC) |
| `root_cause` | enum | 0.20 | nguyên nhân gốc (đường vào + điểm yếu bị lợi dụng) |
| `ioc{}` | tập chuẩn hoá | 0.15 | IOC theo loại (chuẩn của `soc-cnt/reference/coverage-intel.md`) |
| `persistence[]` | tập | 0.10 | cơ chế duy trì `{kind, location}` |
| `remediation[]` | tập | 0.10 | hành động khắc phục |
| `citations[]` | trích dẫn | 0.10 | evidence ID thật |

Sáu trường nội dung này cũng là **6 trường bắt buộc** cần điền ở .001 — dùng đúng tên trường mà
schema/HV-33 trong input quy định.

**Quy trình lập báo cáo từ gói bằng chứng**
1. Kiểm kê gói HV-36: danh sách hiện vật, hash, biên bản thu giữ, chuỗi bàn giao.
2. Dựng timeline (chuẩn hoá UTC) → suy ra root cause (bước sớm nhất có thể chứng minh) → scope (mọi máy
   có dấu vết) → IOC và persistence → remediation tương ứng **từng** backdoor/IOC.
3. **Mỗi khẳng định phải truy được về hiện vật** — .002 yêu cầu trích dẫn dạng
   `{hiện vật, định vị, trích}` (vd `{"artifact": "HV-26", "locator": "LOG-8f2a…", "excerpt": "4624 type 10 …"}`)
   để verifier grep lại. Trích dẫn bằng evidence ID có thật; ID bịa ⇒ mất điểm trích dẫn.
4. Không để ô nào dạng văn xuôi cần người đọc mới chấm được — mọi trường là giá trị/tập/danh sách có cấu
   trúc.
5. Nhất quán số liệu giữa các trường (số máy trong scope = số máy nhắc trong timeline) — xem thêm
   `soc-ir` T1617 về nhất quán Executive/Technical.

## Bẫy hay gặp

- Viết root cause là triệu chứng (cảnh báo đầu tiên) thay vì điểm vào thật.
- Thiếu remediation cho một backdoor đã liệt kê ở persistence.
- Trích dẫn chung chung ("xem log") không trỏ được về bản ghi.
- Báo cáo chính thức trước khi peer review (ngoài đời vi phạm SLA chất lượng).
