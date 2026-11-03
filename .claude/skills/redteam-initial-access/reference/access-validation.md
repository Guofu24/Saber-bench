# Red · Recon, kiểm đường vào và xác nhận quyền truy cập trong lab

Chọn khi chưa có foothold đã xác minh. Giữ target inventory từ observation, session/principal, object IDs,
menu và baseline hợp lệ. Đừng đoán credential, phiên bản lỗ hổng hay đường dẫn không được tool/scenario cấp.

| Nhánh được menu hỗ trợ | Điều cần kiểm | Bằng chứng và điều chưa chứng minh |
|---|---|---|
| Recon ứng dụng/dịch vụ | Resource/route nào thực sự quan sát được, phạm vi nào chưa kiểm | Response/route refs; banner hoặc cổng mở chưa chứng minh khai thác được |
| Authentication | Login outcome gắn đúng principal/session và fixture do scenario cấp | Thành công đăng nhập không tự chứng minh quyền đọc mọi tài nguyên |
| Authorization | Quyền mong đợi từ scenario, object thực trả/thay đổi và principal thực dùng | Mã 200 có thể là error page; mã lỗi vẫn cần xem side effect nếu có bằng chứng |
| Upload/probe trơ | Marker đúng loại, target đúng scope, server receipt và vị trí quan sát | Upload thành công chưa có nghĩa script thực thi hoặc có shell OS |
| Phishing mô phỏng | Tool mail/lab recipient/template trơ thực sự có | Sent/delivered/opened/clicked là các mức riêng; không suy credential compromise |
| Dịch vụ nhiều node | Target node/identity/transport thuộc topology được cấp | App session không tự thành quyền host hoặc AD; không pivot khi thiếu prerequisite |

## Vòng kiểm có giới hạn

Chọn một hypothesis có phép kiểm phân biệt, dùng baseline/negative control khi scenario cung cấp.
Giữ request ID, timestamp, status, response evidence đã redacted và before/after state được phép xem.
Không thay nhiều biến rồi kết luận biến nào gây kết quả; không tiếp tục một probe lỗi nếu không có thông tin mới.
Target ngoài scope, tool không có, auth fixture thiếu: ghi blocked; không tự chế payload hay dùng secret thật.

Nếu tool pending/timeout, reconcile job ID; không thử lại tác động chưa rõ kết quả. Phân biệt:
`not attempted`, `attempted`, `blocked by control`, `executed without objective`, `objective observed`, `unknown`.
Kiểm bằng evidence gắn đúng step; output của lần trước hoặc account khác không được dùng cho claim hiện tại.

## Bàn giao access → impact

Chỉ bàn giao capability đã thấy: principal/session alias, scope resource/action, expiry/revision nếu có,
receipt/evidence, giới hạn và next objective. Không gửi password/token trong note hoặc team message.
Nếu mới có route/baseline, bàn giao như recon finding; không gắn nhãn “compromised host”.
Đích đã bị containment hoặc session hết hiệu lực thì revalidate; không tự mở rộng campaign để né phạm vi.

Nguồn phân loại hành vi: [MITRE emulation](https://attack.mitre.org/resources/adversary-emulation-plans/).
Quy trình kiểm/ghi kết quả: [NIST SP 800-115](https://csrc.nist.gov/pubs/sp/800/115/final).
