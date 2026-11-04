# Recovery · Kế hoạch, restore validation và đưa dịch vụ hoạt động lại

Chọn sau containment/eradication hoặc khi phải kiểm một phương án restore. Input: affected services/data,
trusted baseline/backup provenance, dependencies, actions đã áp dụng, acceptance criteria, owner và RTO/RPO
nếu tổ chức đã đặt. Recovery role của SABER xác minh; restore/change chỉ qua actor/tool có quyền.

## Chuẩn bị phép kiểm

1. Xác định critical business functions và dependency order: identity/DNS/network, database/storage, app,
   integrations, user workflows. Không khởi động tất cả cùng lúc chỉ vì host boot được.
2. Kiểm backup/source time, manifest/hash, consistency, encryption/access và restore prerequisites khi có.
   Backup job success khác recoverability; restore point trước alert chưa chắc trước intrusion.
3. Kiểm entry/control failure đã xử lý tới đâu, persistence/credential scope và evidence đã giữ. Không đưa
   hệ thống trở lại chỉ vì AV không báo; ghi residual risk và quyết định của owner.
4. Định nghĩa expected state và phép kiểm theo từng tiêu chí, thời gian quan sát, abort/rollback condition,
   người chịu trách nhiệm. RTO/RPO phải theo hợp đồng/scenario, không tự đặt số chung.

## Acceptance matrix

| Mặt kiểm | Bằng chứng cần | Giới hạn |
|---|---|---|
| Availability | Service health + request nghiệp vụ đúng đường/identity | HTTP 200/host up chưa chứng minh mọi dependency hoạt động |
| Data integrity | Version/hash/count/transaction hoặc kiểm consistency phù hợp baseline | Hash bằng nhau không chứng minh baseline không nhiễm; snapshot crash-consistent cần kiểm app |
| Access | Người/workload hợp lệ đúng quyền; quyền nguy hiểm đã thu hồi | Login thành công chưa kiểm đọc/ghi hoặc downstream grant |
| Protection | Control/rule/sensor active và phép kiểm được cấp | No alerts không là proof clean; sensor offline có thể tạo im lặng |
| Client work | Event/task hợp lệ tiếp tục từ checkpoint, không duplicate side effects | Notification sent/acknowledged khác công việc hoàn tất |
| Sustainability | Theo dõi trong cửa sổ được giao, errors/backlog và dependencies | Checked tại một tick không bảo đảm mãi mãi |

Restore là thay đổi cần evidence trước/sau và receipt. Job pending/partial cần giữ từng resource status;
không retry destructive restore hoặc release containment khi chưa reconcile. Rerun business test không được
gửi giao dịch/transfer trùng; dùng test data hoặc owner workflow được cấp.

## Cutover, rollback và bàn giao

Đưa kết quả cho IR/lead: tiêu chí passed/failed/unknown, evidence, data-loss window nếu biết, affected users,
remaining controls, pending jobs và owner. Cutover/release do role có quyền quyết định; recovery không tự gỡ chặn.
Nếu fail, giữ trạng thái an toàn trong phạm vi được cấp và bàn giao corrective action; không sửa baseline để báo pass.
Rollback cũng cần kiểm actual state, không chỉ receipt accepted. Giữ bản chứng cứ/backup theo retention/hold hiện có.

Đóng nhiệm vụ khi đã trả lời câu hỏi được giao và bàn giao gaps, không tự đóng incident. Sau case cập nhật
recovery runbook theo failure có evidence: missing dependency, unusable backup, wrong permission hoặc lost
checkpoint; retest trên dữ liệu đại diện trước release lesson.

Ca review: backup success nhưng restore fail; app up nhưng database sai version; user login được nhưng write bị
chặn; protection bị tắt; restore timeout. Báo cáo phải giữ unknown/failed thay vì một nhãn “recovered” chung.

Nguồn: [NIST SP 800-184](https://csrc.nist.gov/pubs/sp/800/184/final).
