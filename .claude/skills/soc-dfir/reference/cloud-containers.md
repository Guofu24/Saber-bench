# DFIR · Cloud, SaaS, container và phạm vi đặc thù

Trước truy vấn, lập inventory account/Region/subscription/project/tenant, log source/type,
retention/hold, quyền đọc, policy lúc xảy ra sự cố và các sink/export hiện có.
SaaS/control plane không mặc định cung cấp disk/RAM hoặc toàn bộ data-plane activity.

## AWS

CloudTrail Event History chỉ 90 ngày management events theo một account/Region, không bao gồm data events.
Trail/Lake, organization scope và các loại event phải kiểm cấu hình riêng. Không có S3 object-read event
không chứng minh không đọc dữ liệu khi data logging chưa bật.
Pivot principal/role ARN, session/AssumeRole chain, eventID/requestID, eventTime, source, resources/outcome;
phân biệt user, service và delegated role. Kiểm IAM/trust/key changes, resource creation, persistence và access
ngoài account/Region đầu tiên. Tham chiếu credential bằng alias/ID được phép, không đưa secret value vào prompt.
Giữ raw exports/config history, pagination và errors; GuardDuty finding không thay nguồn gốc sự kiện.
EBS snapshot cần volume/resource IDs, encryption/access và consistency; không tự chứa RAM.

## Azure / Entra / M365

Tách subscription Activity Log, Entra sign-in/audit, resource diagnostics, Defender findings và Purview Audit.
Kiểm license/quyền/retention, ingestion delay, export job completion, paging/result limits.
Pivot object/service principal/session → subscription/resource/mailbox/site → action/outcome;
review grants/roles, managed identities, Key Vault audit khi có, rules/delegates/sharing và file operations.
Preview/sync/download/export/share là các event khác nhau; số bản ghi API không tự là số tài liệu độc nhất.
Giữ event identity để deduplicate; người có quyền không đồng nghĩa đã truy cập, link public không chứng minh đã có người nhận.

## GCP / Google Workspace

Admin Activity luôn ghi cho hoạt động được hỗ trợ; Data Access thường mặc định tắt trừ BigQuery.
Quyền Logs Viewer không bảo đảm đọc được mọi Data Access log. Kiểm service coverage, sink/exclusion,
bucket retention, project của tài nguyên được truy cập và quyền của người export.
Pivot principal/service account/impersonation, methodName, resourceName, request context và outcome.
Phân biệt control-plane config với dữ liệu người dùng; truy cập tài nguyên công khai có giới hạn ghi audit.
Workspace dùng nguồn activity/admin/login/token/sharing tương ứng; không suy GCP Audit Logs bao phủ mọi SaaS.

## Containers / Kubernetes / CI-CD

Thu pod UID/container ID, namespace/cluster/node, image **digest**, service account, owner reference,
deployment history, runtime/node/ingress logs và API audit trước khi workload biến mất nếu an toàn.
Image tag thay đổi được; cùng pod name sau restart chưa chắc cùng entity.
Audit cần policy/backend và retention; Metadata chỉ ghi metadata, không đủ suy nội dung request/response.
`exec` API audit không tự ghi mọi lệnh shell đã chạy trong phiên; nối runtime/process evidence.

Điều tra RBAC/role binding, workload/daemonset, secret access khi có log, admission changes và cloud workload
identity. So GitOps/IaC, deployment/maintenance records để tách thay đổi được phép.
Nối commit → runner/build → artifact hash/signature → registry → deployed digest; giữ audit/provenance
và xác định chỗ nào trong chuỗi tin cậy có thể đã bị chiếm. Container compromise không tự là node/cluster compromise.
Restart pod/revert commit không chứng minh đã thu hồi credential hay artifact đã phát hành.

## Thu qua API và bàn giao

Giữ account/tenant, endpoint/version, query/time bounds, request/job IDs, page tokens (bảo vệ nếu nhạy cảm),
page/record counts, duplicate handling, throttling/retry và export hash. Một trang 100/1000 record chưa là scope đầy đủ.
Không bypass quota/permission hoặc chạy export ngoài tenant để “lấp dữ liệu thiếu”.
Snapshot/clone là thay đổi tài nguyên: cần quyền/phạm vi cho việc đó; read access không tự cấp create quyền.
Chỉ đề nghị containment/rotation/restore cho owner; lưu receipt và observed effect trước kết luận.

## OT, mobile/BYOD và appliance

Ưu tiên safety/operations owner trong OT; dùng passive/historian/config/change history khi được phép.
Không chủ động scan, reboot PLC/HMI hay cài collector vì chưa có artifact. Với mobile/BYOD, ghi loại
acquisition/MDM/corporate container thực sự được cấp và giới hạn OS/encryption/personal data.
Appliance dùng config/firmware/AAA/remote syslog/HA peer/network evidence; vendor support khi công cụ không đủ.
Đây là nhánh điều phối và phân tích dữ liệu có sẵn, không phải tuyên bố SABER có connector hoặc acquisition cho mọi nền tảng.

Nguồn: [AWS Event History](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/view-cloudtrail-events.html),
[Google Audit Logs](https://docs.cloud.google.com/logging/docs/audit),
[Kubernetes audit](https://kubernetes.io/docs/tasks/debug/debug-cluster/audit/).
