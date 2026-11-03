# Identity · User, workload identity và trust boundary

Chọn khi sign-in/session/permission thay đổi đáng ngờ hoặc cần đánh giá account compromise.
Input: principal/object ID, tenant/domain, account type, time window, auth/access/change logs và baseline quyền.
Credential aliases được phép dùng; không đọc token/password/key value từ provider pool hoặc dump secrets.

## Dựng identity graph

Tách person, user account, service principal/managed identity, device, session/token, role/group/grant và resource.
Cùng username/email chưa là cùng identity giữa tenant; một account có thể nhiều người dùng hoặc automation.
Giữ SID/object ID/session scope, issuer/audience nếu có từ audit và historical membership/change times.
Current permissions là snapshot; không tự chứng minh quyền lúc xảy ra sự cố.

| Câu hỏi | Nguồn cần nối | Cần loại trừ |
|---|---|---|
| Ai đăng nhập và đã làm gì? | Sign-in/MFA/CA + app/resource audit + session/endpoint | Fail→success, VPN/IP mới hoặc impossible travel chưa tự là compromise |
| Quyền nào bị lạm dụng? | Role/group/ACL/grant change + downstream resource actions | Approved PIM/admin workflow, IaC/deployment; entitlement khác usage |
| Workload identity bị dùng sai? | Service principal/role session, consent/credential metadata, resource access | Legitimate automation; không dùng user sign-in logs làm nguồn duy nhất |
| AD/hybrid có mở rộng phạm vi? | DC/endpoint/session + group/GPO/delegation/PKI/sync history | Replication/admin/sync hợp lệ và audit/SACL gaps |
| Thu hồi đã hiệu lực? | Revocation action, application session semantics, subsequent target access | Password reset không đồng nghĩa mọi access token, app session, grant đã mất |

Đánh giá identity abuse, quyền đã dùng và resource impact riêng; risk label/MFA success không xác nhận người
thực đang điều khiển phiên. Theo dấu actor/target riêng trong audit; admin thực hiện revoke không phải actor attack.
Khi cần AD object/event pivots, dùng topic chuyên sâu đã khai báo thay vì suy tất cả từ một Event ID.

## Handoff containment có giới hạn

Đưa IR danh sách principal/session/grant/resources có evidence, scope/timestamps, service dependencies,
desired postcondition và rủi ro gián đoạn. Authority theo tool/runtime; không tự disable domain/rotate mọi key.
Thu hồi có độ trễ và phụ thuộc resource/application; verify subsequent access qua nguồn được cấp.
Giữ break-glass/service continuity theo SOP, không tự tạo ngoại lệ. Action queued chưa là effective;
attempt bị chặn chứng minh tác động hẹp tại lần thử đó, không khẳng định toàn bộ token đã bị hủy.

Sau xử lý, phối hợp recovery kiểm user/workload hợp lệ hoạt động lại và quyền không được nới quá mức.
Finding phải có entity namespace, activity/permission timeline, alternatives, gaps/confidence và owner next step.
Không tự attribution cho người thật, không đưa các trường secret vào notebook hoặc báo cáo.

Ca review: user trùng tên khác tenant; stale session sau reset; service principal ngoài giờ; approved admin
grant; thiếu audit policy. Mỗi kết luận phải phân biệt authentication, authorization và action đã quan sát.

Nguồn: [Microsoft access revocation](https://learn.microsoft.com/en-us/entra/identity/users/users-revoke-access),
[SigninLogs schema](https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/signinlogs),
[AuditLogs schema](https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/auditlogs).
