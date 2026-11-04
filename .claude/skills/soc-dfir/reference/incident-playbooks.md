# DFIR · 12 thẻ tình huống

Chọn theo trigger/câu hỏi và evidence hiện có, không chạy mọi thẻ trên mọi case.
Mỗi thẻ dùng intake → hypothesis → collection/QC → correlate → scope/impact → handoff.
Containment là đề nghị cho role có quyền; không tự thêm lệnh tấn công hay công cụ acquisition.

## PB01 · Ransomware / mã hóa hàng loạt

- Trigger: file đổi/mã hóa, backup tamper, ransom note hoặc gián đoạn có evidence.
- Giữ process/session/auth, remote execution, file changes, note/sample hash, backup/VSS audit,
  network và chứng cứ staging/data read; thu bộ đại diện theo rủi ro, báo ongoing harm ngay.
- Dựng ingress → quyền → lateral → backup impact → exfil/unknown → encryption; so batch hợp lệ.
- Bàn giao affected hosts/trust boundary/backup provenance; cô lập không cần chờ full image nếu đang lan rộng.
  Không đồng nhất mã hóa với exfil hoặc restore thành công với đã loại bỏ đường vào.

## PB02 · Phishing / BEC

- Trigger: mailbox rule/grant lạ, thông điệp thay đổi thanh toán, sign-in bất thường.
- Giữ message/header/trace, sign-in/MFA/CA, rules/delegates/OAuth, mailbox/file actions và business context.
- So legitimate forwarding/delegation, user confirmation qua owner/kênh tin cậy; delivered khác read.
- Bàn giao identity/email/finance owner phạm vi session, recipients và tác động có căn cứ;
  không coi reset password là đã thu hồi grants/tokens/rules.

## PB03 · AD / đặc quyền domain

- Trigger: group/ACL/GPO/delegation/PKI thay đổi trái phép hoặc privileged session đáng ngờ.
- Thu DC + endpoint + PAM/PKI/sync nếu có; nối SID/session, source/target và lịch sử quyền.
- So change ticket, admin automation và nguồn log độc lập; 4672/4769 một mình không chứng minh forest compromise.
- Bàn giao scope/trust graph, persistence/unknown và dependency cho identity/IR;
  không tự reset domain/forest hay coi một host sạch là cả domain an toàn.

## PB04 · Process / fileless / injection

- Trigger: process chain, script/module/memory anomaly, outbound gắn process.
- Thu parent/child, command/hash/signature, session, file/task/service, script logs và RAM khi có lý do/công cụ.
- So admin automation, JIT, parser/symbol errors; corroborate memory findings với nguồn khác.
- Báo observed execution khác inferred payload; lỗi plugin hoặc AV không phát hiện không phải clean.

## PB05 · Web server / web shell / upload

- Trigger: file mới ở web root, worker tạo process, POST/outbound bất thường.
- Thu request IDs, reverse proxy/WAF/app/access/error, auth, filesystem/process/network và deploy history.
- Nối request → route/identity → write/execute → outbound; kiểm upload/deployment hợp lệ.
- Bàn giao entry/control failure, scope dữ liệu/session và persistence; không execute sample,
  không coi xóa file web shell là xử lý xong lỗ hổng/credential.

## PB06 · AWS IAM / assumed role misuse

- Trigger: IAM/trust/API/resource actions lệch baseline, key exposure đã được báo.
- Thu principal/role session, CloudTrail đúng account/Region, IAM/config, data events nếu có và downstream changes.
- So IaC/automation và role chaining; không suy thiếu object reads từ Event History là không exfil.
- Bàn giao credential alias, blast radius, persistence và rotation/dependency cho owner;
  không thu secret value hoặc thử truy cập ngoài scope để xác minh key.

## PB07 · M365 / SaaS exposure

- Trigger: bulk activity, anonymous share, mailbox/file export hoặc app grant đáng ngờ.
- Thu audit/sign-in, object IDs/classification, historical permissions, grants, sharing và export completion.
- Tách preview/sync/read/download/share/recipient; so business export, paging/duplicates và retention gaps.
- Bàn giao dataset, exposure window, recipients known/unknown; không xóa dữ liệu có hold hoặc tự thông báo breach.

## PB08 · Insider / nghi truyền dữ liệu trái phép

- Trigger: DLP/USB/cloud upload hoặc referral đã có phạm vi từ owner/HR/legal.
- Thu đúng data categories: DLP, file/app audit, proxy/process, USB artifacts, authorized exports/job context.
- Tách device connected, file available, copied, transmitted và intent; kiểm nhiệm vụ được phép.
- Báo factual/need-to-know, giữ uncertainty; không tự mở dữ liệu cá nhân ngoài scope hay suy trách nhiệm pháp lý.

## PB09 · Kubernetes workload / secret exposure

- Trigger: image/RBAC/workload/cloud identity changes, exec/egress không theo baseline.
- Giữ pod UID/container/node/namespace, digest, owner/service account, audit/runtime/ingress và GitOps history.
- Tách pod vs node/cluster compromise; Metadata audit không cho biết mọi command/secret bytes.
- Bàn giao identity/RBAC/image lineage và external dependencies; restart pod không xóa cloud grant bị lạm dụng.

## PB10 · CI/CD / supply chain

- Trigger: workflow/token/runner/release changes hoặc artifact provenance bất thường.
- Giữ SCM/pipeline audit, commit/review, runner/build logs, artifact digest/signature, registry/deployment history.
- Nối commit → build → sign → publish → deploy, xác định mắt xích còn tin cậy; so release hợp lệ.
- Bàn giao versions/consumers, credentials/signing/runner scope; revert commit không thu hồi artifact đã phát hành.

## PB11 · Database / API extraction

- Trigger: query/export lớn, tenant/object authorization bất thường hoặc account/key misuse.
- Thu DB/app/API audit, request IDs, auth/session, query/object scope, response metadata khi có và network.
- So batch/analytics, failed vs successful request, data thực trả; deduplicate records/objects và nêu uncertainty.
- Bàn giao dữ liệu/tác động đã chứng minh, authorization gap và owner; quyền SELECT không là số dòng đã lộ.

## PB12 · VPN / appliance / network edge

- Trigger: admin config/auth changes, unknown tunnel/route, session hoặc vendor exposure liên quan case.
- Thu firmware/config/backup diff, AAA/VPN/session, remote syslog, HA peer và upstream/downstream flows.
- Corroborate ngoài appliance nghi bị chiếm; nối identity/session/NAT tới hosts đích, kiểm maintenance.
- Bàn giao scope, management-plane/safety dependencies; không reboot hoặc thay config ngoài quyền được giao.

## Điều kiện bàn giao chung

Finding + evidence IDs + timeline + scope matrix + coverage/unknowns + decision relevance + owner/next test.
Nếu nguồn chưa có, đề nghị collection cụ thể; không tạo output hoặc claim đã thực thi từ danh sách trên.
Các mốc 15/30 phút, SLA và số nguồn trong handbook là ví dụ tổ chức, không tự thành timeout/chất lượng bắt buộc.
