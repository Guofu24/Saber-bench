---
name: soc-identity
description: Điều tra danh tính, đăng nhập, phiên và lạm dụng quyền từ dữ liệu được cấp; phân biệt gõ sai, tác vụ dịch vụ và truy cập trái phép. Bàn giao phương án thu hồi phiên/quyền cho IR, không tự đọc secret.
---

# Điều tra danh tính và quyền truy cập

Trong world, theo [hợp đồng lab](../soc-orchestrator/reference/continuous-world.md).

- Nhận principal/account/session và thời điểm cần đánh giá. Giữ tenant/domain/ID, không gộp account vì cùng tên ngắn.
  Chỉ dùng danh tính trong observation; không đọc key pool, password, token hoặc database nội bộ.
- Nối login, kết quả truy cập, quyền tài nguyên và thay đổi theo thời gian bằng event ID. Chuỗi fail → success,
  vị trí lạ hay tên service account không tự chứng minh compromise hoặc tính hợp lệ.
- Application lab chỉ có principal/session/ACL được cấp. Không suy có AD, IdP cloud, MFA hay token audit thật.
  Artifact identity là snapshot tại lúc thu, không chứng minh quyền lịch sử nếu không có log thay đổi.
- Xác định tài khoản bị dùng trái phép, tài nguyên đã chạm/đã đọc và phần chưa biết; không suy người thật đứng sau
  một principal. Kiểm cách giải thích hợp lệ và bằng chứng trái chiều.
- Ghi finding và bàn giao IR phạm vi thu hồi/chặn hẹp, người dùng bị ảnh hưởng và cách kiểm phục hồi truy cập hợp lệ.
  Không tự vô hiệu hoá account ngoài tool được cấp; không coi thông báo đã gửi là người dùng đã khắc phục.

Tham khảo kiểm chứng: [nhóm cảnh báo](../soc-mon/reference/alert-groups.md).
Hồ sơ: [case record](../soc-orchestrator/reference/case-record.md).
