# DFIR · Truy vấn cloud có phạm vi và kiểm chứng coverage

Chọn khi đã biết tenant/account/project, time window và câu hỏi actor/action/resource.
Các mẫu dành cho operator/case có tool tương ứng, không cấp shell/cloud API cho agent SABER.
Giữ raw result, request/job IDs, query, engine/schema, errors, pages/counts và export hash.

## AWS: management events trước, data events kiểm riêng

Bash, tên Region và thời gian phải theo case; không truyền secret vào command line:

```bash
aws cloudtrail lookup-events \
  --region ap-southeast-1 \
  --start-time 2026-11-01T00:00:00Z \
  --end-time 2026-11-02T00:00:00Z \
  --lookup-attributes AttributeKey=EventName,AttributeValue=AssumeRole \
  --page-size 50 --output json --no-cli-pager > assume-role-events.json
```

Một lookup chỉ lọc một attribute. CLI tự paginate trừ khi bị tắt/giới hạn; kiểm lỗi/throttling và completion.
`CloudTrailEvent` là JSON được chứa trong response: parse ra giữ eventID, eventTime, eventSource/eventName,
userIdentity/sessionContext, sourceIPAddress, resources và errorCode khi có.
Nối role session với subsequent actions trong accounts/Regions được cấp, dùng identity/session/resource refs;
request ID/eventID có mục đích khác nhau, không gộp record tùy tiện.
Event History không trả S3 object data events; cần trail/Lake có cấu hình đó. Không chạy query thiếu nguồn rồi
báo “không exfil”. Snapshot/image forensic cần quyền riêng và source metadata/consistency.

## Entra: sign-in khác directory change

KQL cho workspace đã ingest bảng tương ứng, identity ID đã xác định:

```kusto
SigninLogs
| where TimeGenerated >= datetime(2026-11-01T00:00:00Z)
    and TimeGenerated < datetime(2026-11-02T00:00:00Z)
| where UserId == "USER_OBJECT_ID_FROM_CASE"
| project TimeGenerated, Id, UserId, AppId, IPAddress, ResultType,
    ConditionalAccessStatus, DeviceDetail, CorrelationId
| order by TimeGenerated asc
```

Theo sau bằng AuditLogs trong cửa sổ tương ứng: InitiatedBy, TargetResources, ActivityDateTime,
ActivityDisplayName, Id, CorrelationId, Result. Parse dynamic fields trước khi lọc; kiểm schema của tenant.
User sign-ins không bao phủ mọi service principal/managed identity/non-interactive nguồn khác.
ConditionalAccessStatus hay MFA result không tự chứng minh người dùng chủ động thực hiện action.
M365 data/mailbox activity cần audit riêng; đừng suy từ Entra sign-in rằng đã đọc mọi file có quyền.

## GCP: query filter cụ thể, không nhầm log chưa bật với không có action

Mẫu filter cho Logs Explorer/Logging API; chọn project/resource scope ngoài filter đúng case:

```text
timestamp >= "2026-11-01T00:00:00Z"
timestamp < "2026-11-02T00:00:00Z"
protoPayload.@type="type.googleapis.com/google.cloud.audit.AuditLog"
protoPayload.authenticationInfo.principalEmail="analyst@example.invalid"
```

Identity trên là placeholder. Pivot serviceName, methodName, resourceName, authorizationInfo,
requestMetadata và status; một số service/redaction không có mọi field. Impersonation/delegation cần xem
chuỗi identity liên quan thay vì chỉ principalEmail. Giữ insertId/logName/resource/time để đối chiếu duplicate.
Admin Activity và Data Access có config/quyền xem khác nhau; filter đúng vẫn có thể thiếu data logs.
Kiểm pagination, API row cap, sink/exclusions/bucket retention và ingestion delay. Không bật logging hồi tố rồi
tuyên bố đã khôi phục quá khứ.

## Kiểm kết luận trước bàn giao

Ghi query trả gì, không trả gì, đã hoàn tất hết trang chưa, event schema/version và nguồn gốc raw.
Phân biệt permission denied, successful request, service-side action, object read, export, external recipient.
Giữ unknown khi thiếu data-plane audit; đưa collection request rõ loại nguồn/time window cho cloud owner.
Không tự thay IAM/trail/sink/retention hoặc rotate key trong quá trình query read-only.

Nguồn: [AWS CLI](https://docs.aws.amazon.com/cli/latest/reference/cloudtrail/lookup-events.html),
[SigninLogs](https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/signinlogs),
[AuditLogs](https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/auditlogs),
[Google query language](https://docs.cloud.google.com/logging/docs/view/logging-query-language).
