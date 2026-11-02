# HUNT · Technical Report

Ghi lại **toàn bộ những gì đã xác định được** về cuộc xâm nhập. Threat Hunting và Compromise Assessment lập
**Technical Report kèm đầy đủ bằng chứng số**; IR lập báo cáo kỹ thuật chi tiết cho sự cố. Hạn: báo cáo sơ bộ ≤ 24
giờ; báo cáo chính thức ≤ 24 giờ sau khi xong phân tích **và peer review**.

## Nội dung bắt buộc

| Mục | Nội dung |
|---|---|
| `scope` | máy và tài khoản bị xâm phạm (kèm mức nếu có) |
| `timeline` | các mốc theo thời gian thật, chuẩn hoá UTC |
| `root_cause` | nguyên nhân gốc: đường vào + điểm yếu bị lợi dụng |
| `ioc` | IOC theo loại, đã refang và chuẩn hoá (`../../soc-cnt/reference/coverage-intel.md`) |
| `persistence` | cơ chế duy trì `{kind, location}` |
| `remediation` | hành động khắc phục — **mỗi backdoor/persistence/IOC có một hành động tương ứng** |
| `citations` | trích dẫn bằng chứng cho mọi khẳng định |

Mọi mục là giá trị/danh sách có cấu trúc — **không có ô nào cần người đọc mới hiểu được**.

## Quy trình lập báo cáo từ gói bằng chứng

1. **Kiểm kê gói bằng chứng:** danh sách hiện vật, hash, biên bản thu giữ, chuỗi bàn giao.
2. Dựng **timeline** → xác định **root cause** nếu có bằng chứng đường vào/điểm yếu → **scope** theo mức ảnh hưởng →
   **IOC** và **persistence** → **remediation** cho từng thứ đã tìm thấy.
3. **Mỗi khẳng định truy được về hiện vật** — trích dẫn dạng `{hiện vật, định vị, trích}` để người khác tìm lại được:
   `{"artifact": "Log AD/Windows", "locator": "LOG-8f2a…", "excerpt": "4624 type 10 từ 203.0.113.9"}`.
   Không bịa ID; không trích chung chung kiểu "xem log".
4. **Nhất quán định nghĩa, danh tính và thời điểm chốt** khi đếm scope. Timeline có thể nhắc scanner hợp lệ,
   collector và máy chưa xác nhận bị ảnh hưởng; không đếm tất cả thành máy bị chiếm. Mục chưa rõ ghi thiếu bằng chứng.
5. Peer review trước khi phát hành bản chính thức.

```json
{"scope": ["ws-07", "srv-file-01"], "timeline": [{"t": "2026-10-17T03:12:00Z", "event": "…"}],
 "root_cause": "phishing đánh cắp thông tin đăng nhập VPN", "ioc": {"ipv4": ["…"]},
 "persistence": [{"kind": "scheduled_task", "location": "\\Microsoft\\Windows\\Updater"}],
 "remediation": ["xoá task \\Microsoft\\Windows\\Updater", "đổi mật khẩu an.nv", "chặn 203.0.113.9"],
 "citations": [{"artifact": "…", "locator": "…", "excerpt": "…"}]}
```

## Sai lầm thường gặp

- Ghi root cause là triệu chứng (cảnh báo đầu tiên) thay vì điểm vào thật.
- Có persistence/backdoor mà thiếu hành động khắc phục tương ứng.
- Trích dẫn không trỏ được về bản ghi.
- Phát hành bản chính thức khi chưa peer review.

Nguồn nghiệp vụ: NICE T1104 (catalog SABER).
