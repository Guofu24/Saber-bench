# SOAR trong SOC lab

Mặc định cả ba preset có gateway `soar`, cổng operator `127.0.0.1:7793`.
Blue IR chạy `contain_session`; blue content chạy `enforce_acl` khi có case đọc
tài liệu khác chủ. Playbook khác: `triage`, `release_session`, `revert_acl`.
Gateway kiểm quyền của actor. `triage` chỉ thu thập bằng chứng đã kiểm hash.

Job có ID bền vững, gắn với case và principal lấy từ collector. Model không được
cung cấp URL, command hay target tùy ý. Chỉ đánh dấu `SUCCEEDED` khi hiệu ứng có
receipt, event tương ứng đã tới collector và đọc lại trạng thái application khớp.
Contain có TTL 60 giây; receipt xác nhận trạng thái tại thời điểm kiểm tra.

## Xem và xử lý job không xác định

```powershell
saber lab soar status --bundle runs/my-lab --job-id <UUID>
saber lab soar reconcile --bundle runs/my-lab --job-id <UUID> --reason "Da kiem tra trang thai dich va receipt; khong con thao tac dang cho"
```

Mất phản hồi sau dispatch, restart khi đang thực thi, hoặc hết deadline sẽ giữ
`INDETERMINATE`. Controller chỉ poll, không tự gửi lại hiệu ứng. Operator kiểm tra
log/trạng thái trước khi reconcile. Reconcile ghi lý do và gỡ chặn case; **không**
đổi kết quả cũ thành thành công. Callback cũ cũng không được thực thi lại.

## Kết nối Shuffle hoặc webhook riêng của lab

Sửa spec **trước render**: `soar.backend` là `shuffle` hoặc `webhook`, `endpoint`
là service origin không chứa credential, `external_network` là Docker network
đã tạo với `--internal`. Gắn dịch vụ SOAR tự quản lý vào network này; `lab up`
kiểm tra isolation trước khi start. Không dùng public SaaS cho topology này.

Với Shuffle, khai báo `soar.workflows` ánh xạ tên playbook sang workflow UUID.
Sau `lab credentials`, đặt API credential của Shuffle vào `external_token` trong
`.secrets/soar.json` bằng editor riêng. Cấu hình credential callback của workflow
bằng `callback_token` trong cùng file, không đưa nó vào prompt, script commit hoặc log.

1. Gateway gọi `POST /api/v1/workflows/{id}/execute`, Bearer API credential,
   body `execution_argument` là chuỗi JSON chứa job/case/evidence/callback URL.
2. Workflow parse argument, gọi POST callback URL với Bearer callback credential
   đã cấu hình riêng. Body rỗng; gateway tự lấy action/target đã khóa trong job.
3. Gateway poll `POST /api/v1/streams/results` bằng execution ID và authorization
   riêng do Shuffle trả về. Receipt riêng không xuất cho actor/Office.
4. Shuffle `FINISHED` chưa đủ: gateway vẫn phải kiểm event và trạng thái application.

Webhook dùng giao thức tương tự: `POST /jobs` nhận payload và trả đúng `job_id`;
`GET /jobs/{id}` trả `job_id`, `state=SUCCEEDED` sau callback. Cả hai dùng Bearer
`external_token`. Callback service origin mặc định `http://soar:8080`.

Adapter theo [Shuffle API](https://github.com/Shuffle/shuffle-docs/blob/master/docs/API.md).
Test local dùng server giao thức giả lập cộng application/collector HTTP thật,
bao gồm false completion và mất phản hồi. Nghiệm thu instance Shuffle thật và
workflow cụ thể cần thực hiện trên máy đích; test giao thức không chứng nhận vendor.
