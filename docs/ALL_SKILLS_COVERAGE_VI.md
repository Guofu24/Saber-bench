# Rà nguồn và bổ sung toàn bộ skill nghiệp vụ

Đợt 2026-11-02 bao phủ **15/15 skill nghiệp vụ**: 1 client, 2 red, 12 blue.
DFIR giữ 13 chuyên đề đã mở rộng; đợt này thêm **17 tài liệu** cho các vai còn lại và sửa hướng dẫn cũ
mâu thuẫn với thực tế. Tổng repository: **18 skills, 15 nghiệp vụ, 3 phát triển, 56 references**.
Ba workflow phát triển đã đọc lại; giữ phạm vi task/review và chính sách manual-only hiện có.

Phạm vi hoàn tất là hướng dẫn ra quyết định và tích hợp tài liệu vào runtime SABER. Mỗi vai có đầu vào,
quy trình, cách kiểm kết quả/thất bại, đầu ra bàn giao và tình huống phản chứng. Tài liệu không tự triển khai
tool/connector hay chứng nhận mọi model làm đúng nghiệp vụ. Các chuyên ngành ngoài dữ liệu/công cụ được cấp
phải ghi dependency và chuyển owner, không giả output.

## Nội dung theo từng skill

Số topic gồm tài liệu riêng và tài liệu dùng chung được khai báo trong cùng đội; không phải số agent.

| Skill | Nội dung được bổ sung/giữ | Đầu ra cần review | Topic live |
|---|---|---|---:|
| [client-user](../.claude/skills/client-user/SKILL.md) | Workflow nhân viên/dev/admin/VIP/service/scanner; checkpoint, browser/API errors, retry không gây trùng, SOC notification và tiếp tục việc | Task/object/job refs, done/blocked/pending, bước tiếp và business outcome | 3 |
| [redteam-initial-access](../.claude/skills/redteam-initial-access/SKILL.md) | Campaign objective/scope/budget, recon/auth/access validation, alternative outcomes, phối hợp recon/access | Plan/step receipts, capability đã kiểm, stop reason và handoff | 2 |
| [redteam-post-exploitation](../.claude/skills/redteam-post-exploitation/SKILL.md) | Prerequisites, collection/transfer/impact trong menu lab, cleanup và closeout có receipt | Effect observed/unknown, changes inventory, cleanup pending/verified | 3 |
| [soc-mon](../.claude/skills/soc-mon/SKILL.md) | Alert/raw validation, đa nguồn, queue/storm/dedup/late events, FP/unresolved, bàn giao ca | Case/claim/citations, owner/deadline theo SOP, collection gap | 9 |
| [soc-hunt](../.claude/skills/soc-hunt/SKILL.md) | Hypothesis có thể bác bỏ, scope/coverage, baseline, controls, pivots, negative findings và chuyển detection | Hunt card/query revisions, population đã/chưa rà, findings và retest | 12 |
| [soc-dfir](../.claude/skills/soc-dfir/SKILL.md) | Acquisition, disk/host/RAM/network/AD/cloud, remote collection, tamper, timeline và QA | Evidence register, scope/timeline/finding có provenance và uncertainty | 13 |
| [soc-ir](../.claude/skills/soc-ir/SKILL.md) | Risk-based containment, quyền/SOP, SOAR/job reconcile, partial effects, eradication và recovery handoff | Decision/action ledger, applied/verified, dependency/residual risk | 11 |
| [soc-cnt](../.claude/skills/soc-cnt/SKILL.md) | Detection contract, Sigma/backend/schema, parser/corpus/holdout, FN/FP, rollout/rollback, coverage có bằng chứng | Rule/version/corpus result, actual active state, MON runbook | 8 |
| [soc-orchestrator](../.claude/skills/soc-orchestrator/SKILL.md) | Task dependencies/ack/ownership, competing hypotheses, race/reassign, SITREP và closure | Decision/task graph, handoff evidence, pending risks và owner | 4 |
| [soc-malware](../.claude/skills/soc-malware/SKILL.md) | Sample intake, static/RE/dynamic, Ghidra/IDA limits, memory, IOC provenance, engine failures | Behavior với byte/function/trace locator, verdict có giới hạn, corpus handoff | 6 |
| [soc-network](../.claude/skills/soc-network/SKILL.md) | Zeek/Suricata, DNS/HTTP/TLS/QUIC, PCAP quality, NAT/time/session, exfil mức quan sát | Sensor/flow/packet refs, bytes có scope, alternatives và next collection | 6 |
| [soc-intel](../.claude/skills/soc-intel/SKILL.md) | Intelligence requirement, source reliability/claim confidence, observable/indicator, STIX/TLP, expiry/correction | Sản phẩm theo HUNT/CNT/MON/IR, nguồn và sharing scope | 6 |
| [soc-platform](../.claude/skills/soc-platform/SKILL.md) | Producer→collector→queue→parser→SIEM→rule→SOAR, health, backfill/duplicate, onboarding và rollback | Chặng lỗi, coverage impact, config/receipt và end-to-end verification | 4 |
| [soc-identity](../.claude/skills/soc-identity/SKILL.md) | User/workload identity, AD/hybrid, authentication/authorization/action, grant/session/revoke semantics | Identity graph, historical privileges, containment scope và verify access | 6 |
| [soc-recovery](../.claude/skills/soc-recovery/SKILL.md) | Dependencies, trusted restore source, backup consistency, acceptance matrix, cutover/rollback | Service/data/access/client/protection results; failed/unknown và owner | 4 |

DFIR chi tiết: [DFIR_CAPABILITY_COVERAGE_VI](DFIR_CAPABILITY_COVERAGE_VI.md).
Menu tấn công vẫn giới hạn trong lab đã cấp; nghiên cứu nguồn không thêm payload hoặc target Internet cho red.
Client không chủ động tạo FP hay đọc kế hoạch đội khác. Blue không dùng evaluator truth làm evidence.

## Những hướng dẫn cũ đã sửa

- RAM-first, cấm cô lập VIP, SLA, lịch hunt và service quotas: phân biệt yêu cầu cụ thể của case/SOP
  với quyết định thực tế. Không áp mốc cứng khi operator chưa cấu hình; không trì hoãn báo ongoing harm.
- “Chỉ đọc nên máy giống hệt trước”: sửa thành không chủ động sửa cấu hình và ghi dấu chân collection.
- “Xóa hết hash độc ở mọi nơi”: phân biệt ngăn thực thi/tái tạo với bản evidence/quarantine hợp lệ và vùng chưa rà.
- “Whitelist/chữ ký/backup đọc LSASS là lành”: yêu cầu behavior/function/config và authorization có căn cứ.
- “C2 phải đều/chậm”: nhịp/port chỉ là quan sát; không áp một hình dạng lên mọi đối thủ.
- “Rule test qua là không bỏ lọt”: đo trên corpus có denominator/holdout/limits, giữ TP regressions đã biết.
- Role malware/identity có hướng dẫn sâu dùng chung nhưng live không đọc được: sửa library loader và consultation.

Catalog 55 nhóm NICE / 175 subtasks, scorer và output schemas không đổi. Case benchmark quy định thứ tự,
SLA hoặc hành động cụ thể vẫn phải tuân thủ. Chỉnh hướng dẫn không làm tiêu chí benchmark dễ hơn.

## Nguồn chính thức đã đối chiếu

Các quy trình được viết cho mục tiêu/công cụ SABER; đây là tổng hợp và áp dụng, không phải nguồn chứng nhận repo.
Link công cụ cần kiểm lại theo version cài đặt; `latest` không luôn là bản stable/deployed.

| Nhóm | Nguồn và điểm dùng |
|---|---|
| Client | [RFC 9110](https://www.rfc-editor.org/rfc/rfc9110.html#section-9.2.2): semantics/idempotent retry; [Playwright](https://playwright.dev/docs/actionability): UI actionability khác business success |
| Red | [NIST SP 800-115](https://csrc.nist.gov/pubs/sp/800/115/final): kế hoạch/đánh giá/báo cáo; [MITRE emulation plans](https://attack.mitre.org/resources/adversary-emulation-plans/): nối hành vi theo objective, giới hạn của threat reports |
| MON/lead/IR | [FIRST CSIRT 2.1](https://www.first.org/standards/frameworks/csirts/csirt_services_framework_v2.1): phân dịch vụ/đầu ra; [NIST SP 800-61r3](https://csrc.nist.gov/pubs/sp/800/61/r3/final): IR gắn với risk management |
| HUNT | [Sentinel hunts](https://learn.microsoft.com/en-us/azure/sentinel/hunts): hypothesis→query→evidence→action; [MITRE getting started](https://www.mitre.org/news-insights/publication/getting-started-attck): áp dụng ATT&CK theo use case |
| CNT | [Sigma rules](https://sigmahq.io/docs/basics/rules.html): format/logsource/condition và backend; [YARA](https://yara.readthedocs.io/en/stable/writingrules.html): patterns/conditions theo engine |
| Malware/RE | [NIST SP 800-83r1](https://csrc.nist.gov/pubs/sp/800/83/r1/final), [Ghidra headless](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/RuntimeScripts/support/analyzeHeadlessREADME.md), [Hex-Rays](https://docs.hex-rays.com/core/decompiler.md): phân tích và giới hạn engine; không coi read-only project là sandbox |
| Network | [Zeek conn](https://docs.zeek.org/en/current/reference/logs/conn.html), [Suricata EVE](https://docs.suricata.io/en/latest/output/eve/eve-json-output.html): identifiers/fields phụ thuộc sensor và schema |
| Intel | [FIRST TLP](https://www.first.org/tlp/): sharing scope; [STIX 2.1](https://docs.oasis-open.org/cti/stix/v2.1/os/stix-v2.1-os.html): observable/indicator, IDs/relationships/versions/markings |
| Platform | [OTel telemetry](https://opentelemetry.io/docs/collector/internal-telemetry/) và [resiliency](https://opentelemetry.io/docs/collector/resiliency/): queue/errors/drop và giới hạn resilience; [joint logging guidance](https://www.cyber.gov.au/publication/best-practices-for-event-logging-and-threat-detection): coverage/integrity |
| Identity | [Microsoft revocation](https://learn.microsoft.com/en-us/entra/identity/users/users-revoke-access), [SigninLogs](https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/signinlogs), [AuditLogs](https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/auditlogs): session hiệu lực và nguồn audit khác nhau |
| Recovery | [NIST SP 800-184](https://csrc.nist.gov/pubs/sp/800/184/final): planning/testing/improvement theo business priorities |

## Tài liệu đến agent live

`case` nạp các reference được khai báo. `world`/`range` nạp core + contract + index rồi dùng `consult_skill`:

```json
{"tool":"consult_skill","args":{"topic":"role-workflows"}}
```

Ví dụ cho client; red access có `campaign-planning`, blue malware có `analysis-workflow`.
`{}` liệt kê index, `{"topic":""}` bỏ chọn. Tài liệu dùng chung có ID như `soc-ir--malware-analysis`;
model lấy ID từ index, không truyền file path/URL. Mỗi lượt chỉ chọn một guide, nhận toàn văn ở prompt kế tiếp.
Trong world, consult thành công hủy các action/plan đang chờ và yêu cầu lập kế hoạch mới;
không chạy tiếp action đã lập trước khi đọc guide. Range vốn lập một action mỗi lượt.

Chỉ tài liệu được khai báo cùng đội vào library; client không nhận blue references, red không đọc blue/case
state nhờ tool này. Tài liệu không khai báo, dev workflows, execution contracts và filesystem tùy ý không
thành topic. Executor permissions giữ nguyên; range xử lý consultation tại controller, receipt `guidance_only`.

Library được hash và pin theo skill version. Source mới không sửa world đang chạy; cần world/bundle baseline
mới để nhận nội dung mới. Lesson/rollback giữ library của version gốc; topic selection cũ không chuyển sang
specialty/version khác. Bundle cần render/rebuild, không chép Markdown đè để né manifest hashes.

## Kiểm tra có thể tái lập

```powershell
uv run python scripts/check_skills.py --out runs/skills-all-expanded.json
uv run pytest tests/unit tests/world tests/lab tests/population tests/environments --junitxml=runs/skills-all-regression.xml
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts
uv run mypy --platform win32
uv run mypy --platform linux
uv run python scripts/validate_catalog.py
```

Audit kiểm 18 frontmatters, 56 references, role wiring, symlink/path boundaries và context limits.
Tests consultation kiểm mọi skill nghiệp vụ qua world, cả ba đội qua range, same-team aliases,
cross-team rejection, next prompt, pinned hash/version, restart và không dispatch guidance tới worker.
Đây là HTTP/controller/provider-fixture tests, không phải đánh giá chất lượng suy luận Gemini.

Các ca phản chứng ở từng chuyên đề dùng cho review/corpus tiếp theo: thiếu dữ liệu, stale prerequisites,
malformed/partial outputs, benign near-match, job uncertainty và prompt injection trong evidence.
Không lấy verdict do agent tự viết làm gold, không dùng câu “đủ skills” để suy mọi tool đã tích hợp hoặc
mọi case production đã được kiểm chứng. File DOCX người dùng và key pool không được sửa/commit trong đợt này.
