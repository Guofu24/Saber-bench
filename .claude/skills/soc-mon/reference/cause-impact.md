# MON · Nguyên nhân và tác động

Sau khi biết cảnh báo đúng, bạn phải trả lời **cái gì gây ra** (nguyên nhân gốc, đường vào ban đầu, hệ
thống/tài khoản liên quan) và **nặng tới đâu** (mức sự cố, phạm vi bị ảnh hưởng, nguy cơ với dữ liệu).

## Tìm nguyên nhân của cảnh báo

**Dữ liệu cần:** telemetry tiến trình (cây cha–con, command line, thời điểm), log thô quanh cảnh báo, kho rule
và mapping ATT&CK, thống kê alert theo rule, whitelist, danh mục log source.

**Tìm tiến trình khởi nguồn**
1. Dựng cây cha–con (pid/ppid, thời điểm, command line).
2. Đi ngược từ tiến trình bị cảnh báo lên trên cho tới tiến trình **đầu tiên nằm ngoài hành vi bình thường** —
   thường là ứng dụng nhận nội dung từ ngoài: Office, trình duyệt, mail client, worker của web server, dịch vụ
   bị khai thác.
3. Chọn **khởi nguồn chuỗi độc có bằng chứng**, không mặc định gốc cây OS hay Office là nguyên nhân.
   Phân biệt host + PID + thời điểm tạo để tránh PID reuse; tên tiến trình hợp lệ vẫn có thể bị chiếm/inject.

**Xác định cơ chế khớp rule:** sự kiện nào, vào thời điểm nào (`t0`), thoả điều kiện nào của rule. Viết lại
được câu "rule X khớp vì trường A = … ở sự kiện B lúc t0".

**Xếp nhóm nguyên nhân** — cảnh báo không phải lúc nào cũng do tấn công:

| Nhóm nguyên nhân | Dấu hiệu |
|---|---|
| tấn công thật | chuỗi hành vi độc có bằng chứng |
| hành vi người dùng/quản trị hợp lệ | khớp whitelist, change ticket, đúng vai trò |
| thay đổi môi trường | agent/phần mềm/script mới triển khai đúng thời điểm cảnh báo bắt đầu |
| logic rule quá rộng | rule thiếu điều kiện loại trừ; thống kê cho thấy rule nhiễu từ lâu |

Với tấn công thật, ghi thêm **giai đoạn xa nhất chuỗi đã đạt** (initial access → execution → persistence →
…), **hành động kích rule** (spawn, ghi tệp, kết nối…) và **đối tượng** của hành động.

**Đầu ra**

```json
{
  "classification": "TRUE_POSITIVE",
  "root_process": "winword.exe",
  "t0": "2026-10-17T04:21:30Z",
  "rule_match": "<điều kiện của rule được thoả>",
  "cause_category": "<nhóm nguyên nhân>",
  "attack_stage_reached": "execution",
  "trigger_action": "process_spawn",
  "trigger_object": "powershell.exe",
  "evidence": ["PROC-…", "LOG-…"]
}
```

Chốt `classification` trước — sai nó thì mọi phân tích phía sau đều đi sai hướng. Nếu nguyên nhân là rule
nhiễu hoặc thay đổi môi trường, mở ticket tối ưu cho Content Security.

## Đánh giá tác động và xác định mức sự cố

Đánh giá theo **ma trận hai chiều** của khách hàng: **phạm vi ảnh hưởng × mức độ ảnh hưởng**.

- **Phạm vi:** hệ thống **cấp độ 3 trở lên** (phân loại theo Nghị định 85/2016/NĐ-CP) · hệ thống **core** · **máy
  quản trị** · **máy người dùng VIP** · máy cá nhân.
- **Mức độ:** gián đoạn dịch vụ · lộ lọt · deface · mã hoá dữ liệu · chiếm quyền điều khiển.
- **Kết quả:** mức **Nghiêm trọng / Cao / Trung bình / Thấp** + phạm vi bị xâm phạm.

**Quy trình**
1. Xác định **tài sản bị tác động** và tra danh mục tài sản: cấp độ hệ thống, core hay không, máy quản trị, VIP.
2. Xác định **loại tác động** từ bằng chứng: dịch vụ ngừng? dữ liệu ra ngoài? tệp bị mã hoá? phiên điều khiển
   từ xa?
3. Tra **đúng ô** ma trận = (hàng phạm vi, cột mức độ) và đọc ra mức. **Ghi lại ô đã dùng** — đúng mức mà không
   chỉ ra được ô là đoán, không phải suy ra.
4. Nhiều tài sản/nhiều tác động: lấy ô **nặng nhất** mà bằng chứng chứng minh được.
5. **Phạm vi:** liệt kê host có bằng chứng bị tác động; giữ riêng host nghi vấn/cần kiểm tra, không nâng thành đã bị chiếm.
6. **Nguy cơ dữ liệu** (ba mức): *đã bị trích xuất* / *có nguy cơ* / *không có bằng chứng*. Dựa vào flow ra,
   truy vấn CSDL bất thường, hành vi mã độc. "Không loại trừ" là kết luận hợp lệ khi có truy cập nhưng chưa
   thấy dữ liệu ra.

**Đầu ra**

```json
{
  "severity": "Cao",
  "matrix_cell": "<hàng phạm vi> × <cột mức độ>",
  "scope": ["srv-db-01", "ws-acc-07"],
  "data_risk": "có_nguy_cơ",
  "evidence": ["…"]
}
```

## Sai lầm thường gặp

- Chọn gốc của cả hệ điều hành thay vì khởi nguồn chuỗi độc.
- Chép mức của cảnh báo thay vì tra lại theo ma trận của khách hàng.
- Không tra danh mục tài sản nên hạ mức một máy VIP/hệ thống cấp 3 vì "chỉ là máy trạm".
- Đúng mức nhưng không nói được ô ma trận nào.

Nguồn nghiệp vụ: NICE T1299, T1351 (catalog SABER).
