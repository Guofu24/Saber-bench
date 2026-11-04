# DFIR: phạm vi nghiệp vụ, nguồn và mức kiểm chứng

Đối chiếu ngày 2026-11-02. Skill cũ thiên về lấy case, snapshot và timeline. Bản hiện tại có
**13 chuyên đề, 12 playbook và 12 nhóm hồ sơ**, cộng luồng nhận việc, kiểm chứng giả thuyết,
bảo toàn chứng cứ, bàn giao và rút kinh nghiệm. Mục tiêu là điều tra sự cố doanh nghiệp với dữ liệu
endpoint, identity, network, cloud và ứng dụng được cấp trong SABER.

“Có hướng dẫn” nghĩa là agent nhận được quy trình, nguồn cần tìm, điều kiện kết luận và đầu ra.
“Thực thi được” còn cần tool/target/quyền tương ứng. “Làm đúng ổn định” cần đánh giá trên dữ liệu có
đáp án đã kiểm chứng. Không dùng số lượng file hoặc audit PASS để thay cho hai mức sau.

## Đối chiếu theo công việc

Mỗi hàng phải dẫn tới một kết quả có thể review, không chỉ biết tên công cụ.
Các topic nằm trong [skill DFIR](../.claude/skills/soc-dfir/SKILL.md).

| Nghiệp vụ | Câu hỏi và đầu ra cần có | Topic chính |
|---|---|---|
| Intake và kế hoạch | Điều tra gì, ai/asset nào, cửa sổ nào, quyền hiện có, ongoing harm, hypothesis/alternative/next test | Core; `timeline-reporting` |
| Acquisition và custody | Thu nguồn nào theo volatility/risk; evidence ID, method/version, hash/bytes, manifest, transfer/access, partial/errors | `acquisition` |
| Disk/filesystem | Chọn đúng volume/offset/sector; file/stream/inode lineage, deleted/carved limitations, working copy và derivative | `disk-filesystems` |
| Windows endpoint | Process/session/persistence/file artifacts, timestamps và điều kiện nguồn đáng lẽ ghi nhận hành vi | `host-forensics`; `windows-ad-investigation` |
| Linux/macOS | Auth, services/jobs, execution/filesystem và OS-specific artifacts; không coi shell history là toàn bộ hoạt động | `host-forensics` |
| RAM | Image integrity, compatibility/symbols, process/module/network pivots, cross-view và benign alternatives | `memory-malware` |
| Malware/RE handoff | Static/dynamic findings, sample/hash/provenance, engine/job receipt, limits; chuyển việc RE sâu cho `soc-malware` | `memory-malware` |
| Network | DNS/flow/PCAP/proxy, NAT/session/time correlation, transport so với nội dung, quan sát và phần chưa giải mã | `network-identity` |
| Email/BEC | Message/trace, rules/delegates/grants, identity và mailbox actions; delivered/read/export phân biệt rõ | `network-identity`; PB02 |
| AD/identity | Logon/process/object graph, audit/SACL, privilege/trust scope, session/token/grant và actor attribution có căn cứ | `windows-ad-investigation`; `network-identity` |
| AWS/Azure/GCP | Actor/action/resource theo account/tenant/project; management/data-plane coverage, exact query và pagination | `cloud-containers`; `cloud-query-recipes` |
| SaaS/API/database | Historical permissions, object/query/export evidence, scope/recipients, dedup và số liệu có giới hạn | `cloud-containers`; PB07/PB11 |
| Container/Kubernetes | Pod/container/node IDs, digest, RBAC/service account, audit levels, runtime và GitOps history | `cloud-containers`; PB09 |
| CI/CD/supply chain | Commit → build → sign → publish → deploy; mắt xích còn tin cậy, versions/consumers bị ảnh hưởng | `cloud-containers`; PB10 |
| Thu từ xa/fleet | Artifact definition/dependencies, scope/caps, flow/job ID, offline collector, completion/partial và readiness gaps | `remote-collection` |
| Anti-forensics | Tamper hypothesis so với rotation/restore/outage/parser error; corroboration và nguồn không đáng tin | `antiforensics-validation` |
| Timeline/root cause/impact | Raw time/offset/skew/uncertainty, causal edges có evidence, scope matrix và control failure/unknown | `timeline-reporting` |
| Báo cáo/handoff/QA | Finding truy về raw record, alternatives/confidence, owners/dependencies, peer review và conditional lessons | `timeline-reporting`; `queries-validation` |

12 playbook: ransomware; phishing/BEC; AD; fileless/injection; web shell; AWS IAM;
M365/SaaS; insider/data transfer; Kubernetes; CI/CD; database/API; VPN/appliance.
Các playbook nối câu hỏi → chứng cứ → kiểm giải thích hợp lệ → điều kiện bàn giao; không chạy tất cả trên mọi case.

OT/ICS, mobile acquisition, hardware/chip-off và thiết bị chuyên dụng được nhận diện để chuyển đúng chuyên gia.
Skill không tự nhận là hướng dẫn đầy đủ cho những chuyên ngành đó. Quyết định pháp lý/thông báo, khôi phục forest
và phê duyệt containment vẫn thuộc owner/role có quyền; DFIR cung cấp chứng cứ và rủi ro cho quyết định.

## Nghiên cứu bổ sung từ nguồn chính thức

Handbook được [review riêng](DFIR_HANDBOOK_REVIEW_VI.md). Các nguồn dưới đây bổ sung quy trình thực hành
và sửa suy luận quá rộng; không chép nguyên manual vào prompt. Cú pháp là mẫu cho case/operator có công cụ,
chưa phải kết quả chạy công cụ trên một evidence image hay tenant thật.

| Nguồn đã đối chiếu | Áp dụng vào skill |
|---|---|
| [NIST SP 800-86](https://csrc.nist.gov/pubs/sp/800/86/final) và [800-61r3](https://csrc.nist.gov/pubs/sp/800/61/r3/final) | Collection/examination/analysis/reporting gắn với IR và rủi ro; không để thứ tự thu cứng cản xử lý ongoing harm |
| [SWGDE Acquisition 2.1](https://www.swgde.org/documents/published-complete-listing/17-f-002-2-1/) và [Examination 2.0](https://www.swgde.org/documents/published-complete-listing/18-f-001-2/) | Ghi phương pháp, tính toàn vẹn, tác động và giới hạn; kiểm công cụ/phương pháp, bảo toàn original/derivative |
| [TSK mmls](https://www.sleuthkit.org/sleuthkit/man/mmls.html), [fsstat](https://www.sleuthkit.org/sleuthkit/man/fsstat.html), [fls](https://www.sleuthkit.org/sleuthkit/man/fls.html), [icat](https://www.sleuthkit.org/sleuthkit/man/icat.html) | Quy trình đi từ partition tới metadata và bytes; offset tính bằng sector, sector size phải xác minh |
| [Plaso log2timeline](https://plaso.readthedocs.io/en/latest/sources/user/Using-log2timeline.html) | Storage file, extraction/parser warnings, provenance và kiểm coverage trước khi kết luận timeline đầy đủ |
| [Velociraptor collection](https://docs.velociraptor.app/docs/clients/artifacts/), [limits](https://docs.velociraptor.app/docs/artifacts/resources/), [offline](https://docs.velociraptor.app/docs/deployment/offline_collections/) | Flow/collection state, artifact dependencies, offline build và resource caps; limits không bao phủ mọi external tool |
| [Microsoft 5136](https://learn.microsoft.com/en-us/previous-versions/windows/it-pro/windows-10/security/threat-protection/auditing/event-5136) và [4662](https://learn.microsoft.com/en-us/previous-versions/windows/it-pro/windows-10/security/threat-protection/auditing/event-4662) | Audit/SACL, cặp thay đổi giá trị, object/session fields; thiếu event chưa loại trừ access/change |
| [Defender process schema](https://learn.microsoft.com/en-us/defender-xdr/advanced-hunting-deviceprocessevents-table) và [network schema](https://learn.microsoft.com/en-us/defender-xdr/advanced-hunting-devicenetworkevents-table) | KQL theo device/time và process lifetime; ghi nguồn DfE/caps/coverage thay vì join PID đơn lẻ |
| [AWS lookup-events](https://docs.aws.amazon.com/cli/latest/reference/cloudtrail/lookup-events.html) và [Event History](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/view-cloudtrail-events.html) | CLI pagination và identity/session pivots; Event History không thay cho S3 object data events |
| [SigninLogs](https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/signinlogs) và [AuditLogs](https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/auditlogs) | Tách sign-in và directory change, kiểm dynamic fields, các nguồn service principal/non-interactive cần riêng |
| [Google query language](https://docs.cloud.google.com/logging/docs/view/logging-query-language) và [Audit Logs](https://docs.cloud.google.com/logging/docs/audit) | Filter time/identity có scope; Data Access config/quyền xem và missing telemetry phải được kiểm riêng |
| [MITRE T1070.006](https://attack.mitre.org/techniques/T1070/006/) | Kiểm timestomp bằng nhiều nguồn; chênh SI/FN không tự chứng minh tamper và không phát hiện mọi biến thể |

## Agent live nhận chuyên đề thế nào

`case` nạp cả 13 chuyên đề. `world`/`range` nạp core + contract + index, rồi blue gọi tool ví dụ:

```json
{"tool":"consult_skill","args":{"topic":"windows-ad-investigation"}}
```

Đây là action model gửi controller, không phải lệnh PowerShell. Lượt suy luận tiếp theo nhận toàn văn
chuyên đề đã chọn. `{}` liệt kê topic, `{"topic":""}` bỏ chọn; chuyển topic khi câu hỏi đổi nhánh.
Mỗi request chỉ thêm một chuyên đề; không cần quyền mở file hoặc truy cập Internet từ agent.

Library được chụp và hash trong skill version. Đọc từ checkout mới không thay world đang điều tra;
restart/lesson/rollback giữ đúng bản. World cũ chưa có library cần baseline world/bundle mới.
Render/rebuild lại bundle khi chuyển máy; không sửa Markdown bên trong bundle để né manifest.

Range xử lý tra cứu tại controller. Receipt ghi `guidance_only`, không có PID hay artifact acquisition giả.
Client/red hiện cũng có tool này cho tài liệu thuộc phạm vi của họ; không đọc được library DFIR.
Nội dung observation, đường dẫn và URL do model đưa vào không thay library.
Hướng dẫn TSK/Velociraptor/cloud không tự cài các công cụ hay mở quyền thực thi chúng.

## Kiểm tra và cách tái lập

Các số đo bên dưới thuộc checkpoint DFIR `bd5f3ff`. Đợt mở rộng toàn bộ đội và kết quả hiện tại nằm ở
[ALL_SKILLS_COVERAGE_VI](ALL_SKILLS_COVERAGE_VI.md); không dùng số reference lịch sử làm tổng hiện tại.

```powershell
uv run python scripts/check_skills.py --out runs/dfir-reference-expanded-audit.json
uv run pytest tests/unit tests/world tests/lab tests/population tests/environments --junitxml=runs/dfir-expanded-regression.xml
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts
uv run mypy --platform linux
uv run mypy --platform win32
uv run python scripts/validate_catalog.py
```

Audit: **PASS, 18 skills / 15 nghiệp vụ / 39 references**, không reference bị bỏ rơi.
DFIR có 13 topic, index 869 ký tự; context `case` 63.647/64.000, `world` 17.463/18.000,
`range` 12.525/18.000. Chuyên đề thêm theo yêu cầu có trần 12.000 riêng; số đo là ký tự, không phải token.

| Kiểm tra tại đợt mở rộng | Kết quả |
|---|---|
| Unit/world/lab/population/environments | 324 passed, 1 skipped, 0 failures/errors; 294 giây |
| Test Chrome tích hợp | Skip vì không đặt `SABER_TEST_CHROME`; đợt này không xác nhận browser thật |
| Ruff lint / format | PASS; 309 file đúng format |
| Mypy Linux / Windows | PASS; 201 source files mỗi nền tảng |
| Frozen catalog | PASS; 55 nhóm NICE / 175 subtasks, không đổi đáp án |
| Skill-creator validator cho `soc-dfir` | PASS, chạy Python với `-X utf8` trên Windows |

Artifacts local: `runs/dfir-reference-expanded-audit.json` và `runs/dfir-expanded-regression.xml`;
không đưa dữ liệu run vào Git. Checkpoint runtime trước đó có riêng 62 tests đã qua.

Tests tra cứu kiểm nội dung xuất hiện ở prompt kế tiếp, HTTP/controller thực, role/path/argument rejection,
hash/corruption, version snapshot, lesson inheritance và restart. Provider trong test là fixture;
không gọi Gemini hoặc đọc key pool. Các mẫu cloud/TSK/EDR được đối chiếu manual, chưa chạy trên dịch vụ/image thật.

Tiêu chí đánh giá hành vi nằm trong topic `queries-validation`: positive/benign/partial/malformed,
clock uncertainty, hash mismatch, audit tắt, pagination và prompt injection trong evidence.
Cần ghi kết quả provider trên corpus đã kiểm chứng trước khi tuyên bố agent làm đúng nghiệp vụ ổn định.
Thêm nguồn mới khi phát hiện một thiếu sót cụ thể; kiểm schema/version và hồi quy, không lấy log/model verdict làm gold.
