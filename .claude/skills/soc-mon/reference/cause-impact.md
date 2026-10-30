# MON · Nguyên nhân và tác động — T1299 (nguyên nhân cảnh báo) · T1351 (tác động)

Sau khi biết cảnh báo đúng, Tier 1/2 phải trả lời **cái gì gây ra** (root cause, initial access
vector, hệ thống/tài khoản liên quan) và **nặng tới đâu** (mức sự cố + scope of compromise).

---

## T1299 — Xác định nguyên nhân của cảnh báo mạng

| Subtask | Mode | Đầu vào | Phải nộp | Chấm |
|---|---|---|---|---|
| **T1299.001** | file | HV-15 cây tiến trình | `root_process` | enum 1.0 |
| **T1299.002** | file | HV-02, HV-15 | `root_process`, `t0`, `rule_match` | 0.5 / 0.25 (±5′) / 0.25 |
| **T1299.003** | soc (EDR, SIEM) | HV-01 02 04 05 06 15 40 | xem dưới | Σwᵢsᵢ, **cap 0.30 nếu classification sai** |

**Tìm tiến trình khởi nguồn (`root_process`)**
1. Dựng cây cha–con từ HV-15 (pid/ppid, thời điểm, command line).
2. Đi ngược từ tiến trình bị cảnh báo lên trên cho tới tiến trình **đầu tiên nằm ngoài hành vi bình
   thường** — thường là ứng dụng nhận nội dung từ ngoài (Office, trình duyệt, email client, web server
   worker, dịch vụ bị khai thác) chứ không phải `explorer.exe`/`services.exe`/`init`.
3. Không chọn tiến trình hệ thống gốc của cả cây; chọn **khởi nguồn chuỗi độc hại**. Tên được chuẩn hoá
   về basename chữ thường.

**T1299.002** — `t0` là **thời điểm** sự kiện khởi nguồn (dung sai ±5 phút; dùng đúng đơn vị/định dạng
của input); `rule_match` là **cơ chế làm rule khớp** (trường/điều kiện nào trong rule được thoả bởi
sự kiện nào) — chọn trong tập giá trị đề cung cấp.

**T1299.003 — dựng trọn chuỗi nhân quả** (đã có hồ sơ mẫu `T1299_0001`)

| Field | Trọng số | Cách xác định |
|---|---|---|
| `classification` | 0.30 | TP/FP/không kết luận — **chốt trước, sai là trần 0.30** |
| `cause_category` | 0.30 | nhóm nguyên nhân: hành vi người dùng hợp lệ, cấu hình/thay đổi môi trường, rule logic sai, hay tấn công thật |
| `attack_stage_reached` | 0.20 | giai đoạn xa nhất chuỗi đã đạt (initial access → execution → persistence → …) |
| `trigger_action` | 0.10 | hành động cụ thể kích rule (spawn, ghi file, kết nối…) |
| `trigger_object` | 0.10 | đối tượng của hành động (file/tiến trình/đích kết nối) |

Đối chiếu HV-40 whitelist và HV-05 kho rule: một cảnh báo do **rule logic quá rộng** hoặc **thay đổi
môi trường** (agent mới, script mới) là nguyên nhân hợp lệ khác "tấn công". HV-06 thống kê alert theo
rule giúp nhận ra rule nhiễu.

---

## T1351 — Xác định tác động của hoạt động độc hại

Đánh giá theo **ma trận hai chiều** (HV-39): **phạm vi ảnh hưởng** × **mức độ ảnh hưởng**.

- Phạm vi: hệ thống **cấp độ 3 trở lên** · hệ thống **core** · **máy quản trị** · **máy người dùng VIP**
  · máy cá nhân. Cấp độ hệ thống theo **Nghị định 85/2016/NĐ-CP** (ghi trong HV-38).
- Mức độ: gián đoạn dịch vụ · lộ lọt · deface · mã hoá dữ liệu · chiếm quyền điều khiển.
- Đầu ra: mức **Nghiêm trọng / Cao / Trung bình / Thấp** + scope of compromise.

| Subtask | Mode | Đầu vào | Phải nộp | Chấm |
|---|---|---|---|---|
| **T1351.001** | file | HV-39 | `severity` | enum 1.0 |
| **T1351.002** | file | HV-38, HV-39 | `severity`, `matrix_cell` | severity × (1.0 nếu đúng ô, **0.5 nếu sai ô**) |
| **T1351.003** | soc (EDR, SIEM) | HV-02 15 16 22 26 31 34 37 38 39 | `severity`, `matrix_cell`, `scope[]`, `data_risk` | (0.5·sev + 0.3·F2 scope + 0.2·data_risk) × [matrix_cell] |

**Quy trình chấm mức**
1. Xác định **tài sản bị tác động** và tra HV-38: cấp độ hệ thống, core hay không, máy quản trị, VIP.
2. Xác định **loại tác động** từ bằng chứng (dịch vụ ngừng? dữ liệu ra ngoài? file bị mã hoá? phiên
   điều khiển từ xa?).
3. Tra đúng **ô** trong HV-39 = (hàng phạm vi, cột mức độ) ⇒ đọc ra severity. Ghi `matrix_cell` theo
   đúng cách HV-39 định danh ô (nhãn hàng/cột hoặc ID ô).
4. Nếu nhiều tài sản/tác động: lấy ô **nặng nhất** mà bằng chứng chứng minh được.

**Vì sao `matrix_cell` là gate:** đúng mức mà sai ô là **đoán trúng**, không phải suy ra — nên chỉ được
một nửa điểm (.002), và ở .003 sai ô thì nhân 0 toàn bài.

**T1351.003 — phạm vi và nguy cơ dữ liệu**
- `scope[]`: danh sách host bị tác động (F2 ⇒ bỏ sót đắt hơn báo thừa; host chuẩn hoá tên ngắn).
- `data_risk`: thang 3 mức về dữ liệu (đã bị trích xuất / có nguy cơ / không có bằng chứng — lấy đúng
  nhãn từ `options` của input). Dựa trên flow ra (HV-22), truy vấn CSDL bất thường (HV-31), hành vi mã
  độc (HV-34). "Không loại trừ" là kết luận hợp lệ khi có truy cập nhưng không thấy bằng chứng ra ngoài.
- Đề cố tình phủ đủ 4 mức và **ô biên**: máy VIP, hệ thống cấp 3 — đừng hạ mức một máy chỉ vì nó là
  "máy trạm" khi HV-38 đánh dấu VIP.

## Bẫy hay gặp

- Chọn root process là tiến trình gốc của cả hệ điều hành thay vì khởi nguồn chuỗi.
- Chép severity gốc của cảnh báo thay vì tra lại theo ma trận khách hàng.
- Đúng severity nhưng không ghi được ô ma trận đã dùng.
- Không tra HV-38 nên bỏ lỡ máy VIP/hệ thống cấp 3.
