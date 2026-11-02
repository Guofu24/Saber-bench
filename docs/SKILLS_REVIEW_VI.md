# Rà soát nội dung skills — 2026-11-01

> Báo cáo lịch sử tại checkpoint `32cfddd` (11 skills). Đợt bổ sung sau báo cáo đã nâng lên
> 18 skills / 12 chuyên môn blue và triển khai evidence query, task/handoff, notebook,
> wait/finish, artifact, rule testing và recovery. Xem [trạng thái hiện tại](SOC_SPECIALISTS_VI.md).
> Mục thiếu sót điều phối bên dưới mô tả tình trạng trước bổ sung; lịch làm việc/campaign
> phức tạp, native adapter và đánh giá chất lượng model vẫn là việc tiếp theo.

## Kết luận

**Trước lượt rà này, skills có khung vai trò và độ phủ chủ đề, nhưng chưa đúng và đủ về cách ra quyết định.**
Một số handbook khuyến khích suy luận thiếu bằng chứng, trái với nguyên tắc ở SKILL chính. Client/red thiếu
hướng dẫn giữ mục tiêu qua nhiều lượt; cơ chế phối hợp nhiều agent còn được mô tả chung chung.

Đã sửa những điểm nêu dưới đây và bổ sung quy trình theo khả năng runtime hiện có. Có thể dùng bộ hướng dẫn này
cho phát triển/đánh giá application lab và các task được cấp đúng dữ liệu/công cụ. **Chưa có cơ sở gọi đây là SOC
tự vận hành hoàn chỉnh, hoặc kết luận Gemini thực hiện đúng toàn bộ playbook.** Trạng thái vẫn là `DEV_SIMULATION_ONLY`.

Lượt này thay đổi Markdown, không triển khai thêm desktop, công cụ tấn công hay backend SOC.

## Đã đối chiếu với gì

- Toàn bộ **11 SKILL.md + 25 reference**: 8 skill nghiệp vụ và 3 workflow phát triển.
- Yêu cầu người dùng: công việc client bình thường; red có mục tiêu và hiệu ứng quan sát được; blue bảo vệ người dùng;
  nhiều thành viên với chuyên môn riêng; hoạt động liên tục; lựa chọn local/sandbox/VM/remote.
- [Catalog đóng băng](../catalog/subtasks.json): **55 NICE task / 175 subtask**, gồm MON 58, CNT 15, HUNT 39, IR 63;
  [phạm vi subtask](SUBTASK_SCOPE.md), [thiết kế agent](AGENT_POPULATION_H4_DESIGN_VI.md),
  [hợp đồng đầu ra](SUBMISSION_CONTRACT_VI.md), [ranh giới thực thi](SECURITY.md).
- Code thực tế: [loader](../src/saber/agents/skills.py), [planner](../src/saber/world/agents.py),
  [scheduler/fallback](../src/saber/world/runtime.py), [observation](../src/saber/world/environment.py),
  [vai và tool](../src/saber/world/models.py).

Không sửa catalog/source/scorer để làm cho hướng dẫn dễ đạt điểm. Định dạng đầu ra, phạm vi và chính sách cụ thể
vẫn do từng task cung cấp. Ví dụ trong handbook không được ghi đè schema của task.

## Theo yêu cầu gốc

| Yêu cầu | Mô tả sau sửa | Giới hạn thực thi/kiểm chứng |
|---|---|---|
| Client là người thường, nhân viên, dev, admin; làm việc bình thường | Theo mục tiêu công việc, quyền, tiến độ; nhận lỗi và thông báo; không chủ động tối đa hoá FP | World có tài liệu/API/bảo trì ứng dụng tổng hợp; chưa phải desktop/browser/email/SSH thực |
| Client có thể biết hoặc không biết bị tấn công | Chỉ biết từ kết quả thao tác và thông báo thực nhận; không đọc kế hoạch red | Chưa đánh giá hành vi model trong nhiều kịch bản kín/hiện; không suy nhận thức từ nhãn đội |
| Red có mục tiêu truy cập/thu thập/gián đoạn | Recon → access → impact theo kết quả và menu; có bàn giao, kiểm kết quả, không ép đủ mọi giai đoạn | Hiệu ứng nằm trong ứng dụng lab; không tương đương foothold OS, C2 hay exfil khỏi lab |
| Blue giám sát, hunting, DFIR, IR, content, lead | Rõ sản phẩm bàn giao, căn cứ, điều chưa biết, xác minh sau phản ứng và ảnh hưởng client | DFIR/IR có tool khác nhau; skill không tự cấp RAM, PCAP, EDR hay reverse engineering |
| Nhiều thành viên phối hợp | Owner/case/ID, việc đã làm, kết quả, việc chờ và người tiếp; tránh trùng hành động | Quy ước prompt chưa thay cho lock/ack/transaction hoặc phân bổ chiến dịch được cưỡng chế |
| Chạy liên tục | Note ngắn, đọc observation mới, giữ tiến độ; scheduler quản lý vòng đời | Hết plan hoặc `actions: []` sẽ dùng scripted fallback; chưa có pause/stop chiến dịch từ ý định LLM |
| Nhịp người thật, lịch làm việc, công việc dài | Skill hướng dẫn mục tiêu và tiến độ; không tự giả lịch nghỉ | Interval tick và fallback chưa tạo lịch ca/nghỉ, workflow ứng dụng đa bước được bảo đảm hoặc memory dài hạn |
| Sandbox / máy mạnh dựng VM / môi trường khác | Phân biệt nơi đặt runtime với năng lực được cấp | Chuyển profile không tự tạo máy nạn nhân, desktop hay toàn bộ hệ SOC |
| Quota và pool keys theo đội | Skill không được đọc/quản lý key; provider/control plane phụ trách | Lượt này không gọi provider, không thử quota/activation; không đọc/in key pool |

## Các lỗi nội dung đã sửa

| Vấn đề trước sửa | Hướng dẫn sau sửa | Tài liệu chính |
|---|---|---|
| 403/404 được coi là chắc chắn khai thác thất bại; 200 dễ bị coi là thành công | Tách claim, attempt, quyền, thành công và impact; đối chiếu backend/telemetry, giữ unknown | [MON alert groups](../.claude/skills/soc-mon/reference/alert-groups.md) |
| Fail → success hoặc mở handle LSASS được diễn giải thành brute force/dump | Kiểm phiên, nguồn, ngữ cảnh và hiệu ứng; dấu hiệu đơn lẻ chưa đủ | [MON validation](../.claude/skills/soc-mon/reference/alert-validation.md) |
| IP private/cổng quen bị loại khỏi hunt | Xét cả C2/lateral nội bộ; kiểm process, đích, quyền, baseline | [HUNT exposure](../.claude/skills/soc-hunt/reference/exposure-review.md) |
| Chữ ký/whitelist được coi là lành; không chữ ký + nhiều API bị coi là độc | Phân loại theo nội dung, hành vi và nguồn; ghi thiếu dữ liệu nếu chưa đủ | [HUNT file](../.claude/skills/soc-hunt/reference/file-malware-hunt.md), [IR malware](../.claude/skills/soc-ir/reference/malware-analysis.md) |
| Hạ chữ toàn URL, bỏ dấu `/`, loại IP nội bộ mặc định | Giữ raw value/nguồn, chuẩn hoá theo loại, áp quy tắc so sánh case trên bản riêng | [CNT intel](../.claude/skills/soc-cnt/reference/coverage-intel.md) |
| AV/prefetch lịch sử tự động chứng minh compromise; phát hiện lặp tự động chứng minh cleanup thất bại | Liên kết đúng binary, phiên, thời điểm, hành động và trạng thái hoàn tất; phân biệt tái nhiễm/kho cách ly | [HUNT intrusion](../.claude/skills/soc-hunt/reference/intrusion-analysis.md), [IR evidence](../.claude/skills/soc-ir/reference/evidence-forensics.md) |
| Entropy cao chắc chắn là packed; image khác disk chắc chắn hollowing | Các đầu mối cần chứng cứ bổ sung; xét relocation/hotpatch/JIT và giới hạn công cụ | [IR malware](../.claude/skills/soc-ir/reference/malware-analysis.md), [IR evidence](../.claude/skills/soc-ir/reference/evidence-forensics.md) |
| Mọi case phải đủ sáu mốc; bỏ domain account; host đầu quan sát = Patient Zero | Không bịa pha/thời gian; giữ identity; phân biệt điểm vào thật và đầu tiên thấy được | [IR reconstruction](../.claude/skills/soc-ir/reference/reconstruction.md) |
| Số host bị ảnh hưởng bằng mọi host trong timeline; phạm vi thà báo thừa | Dùng định nghĩa scope chung, phân mức có căn cứ; không tính scanner/collector thành nạn nhân | [HUNT report](../.claude/skills/soc-hunt/reference/reporting.md), [IR triage](../.claude/skills/soc-ir/reference/triage-coordination.md) |
| C2 phải đều/nhỏ; hai đỉnh Diamond đủ quy kết | Đây là đầu mối/mô hình tổ chức giả thuyết; cần bằng chứng phân biệt và xét khả năng khác | [IR network](../.claude/skills/soc-ir/reference/network-attribution.md) |
| Kế hoạch cô lập trước thu chứng cứ mâu thuẫn yêu cầu RAM-first | Theo phụ thuộc/SOP; giữ yêu cầu RAM trước cô lập/kill của case | [IR containment](../.claude/skills/soc-ir/reference/containment-eradication.md) |
| Dẫn RFC như thứ tự cố định; cú pháp headless thiếu project name | Tách SOP case với nguyên tắc volatility; sửa cú pháp và mô tả chính xác công cụ chưa được cấp | [IR evidence](../.claude/skills/soc-ir/reference/evidence-forensics.md), [IR malware](../.claude/skills/soc-ir/reference/malware-analysis.md) |
| Client tạo FP như mục tiêu; red làm hết chuỗi và dừng bằng câu nói | Client hoàn thành công việc; red chọn bước có mục đích, bàn giao kết quả; control plane quyết định dừng | [Client](../.claude/skills/client-user/SKILL.md), [Red access](../.claude/skills/redteam-initial-access/SKILL.md), [Red impact](../.claude/skills/redteam-post-exploitation/SKILL.md) |
| Bàn giao chung chung; bên có ID bằng chứng là thắng | So chất lượng/claim/thời điểm, giữ bất đồng, giao phép kiểm; tách DFIR với IR | [Lead](../.claude/skills/soc-orchestrator/SKILL.md), [case record](../.claude/skills/soc-orchestrator/reference/case-record.md) |
| Parser/Suricata và phát hành rule thiếu bước kiểm chứng | Engine/version, replay, field/type/lỗi parse, corpus có căn cứ, rollout và rollback | [CNT authoring](../.claude/skills/soc-cnt/reference/rule-authoring.md) |

Các giới hạn chung về schema, tenant, cutoff, chất lượng bằng chứng nằm trong case record; mode world nhận
hướng dẫn tương ứng trực tiếp từ [continuous-world](../.claude/skills/soc-orchestrator/reference/continuous-world.md).
Sửa reference mà world không nạp sẽ không đủ: vì vậy các nguyên tắc cốt lõi cũng đã đưa vào entrypoint/world contract.

Nguồn kỹ thuật dùng để kiểm tra một số câu dễ sai:

- Chữ ký hợp lệ vẫn có thể xuất hiện trên mã độc: [MITRE T1553.002](https://attack.mitre.org/techniques/T1553/002/).
- URL scheme/host và các thành phần còn lại có quy tắc phân biệt hoa thường khác nhau:
  [RFC 3986 §6.2.2.1](https://www.rfc-editor.org/rfc/rfc3986.html#section-6.2.2.1).
- [RFC 9110 §15](https://www.rfc-editor.org/rfc/rfc9110.html#section-15) định nghĩa status HTTP.
  Việc cần telemetry để kết luận tác động bảo mật là suy luận áp dụng trong review, không phải RFC chứng nhận kết quả một vụ tấn công.
- Bảo toàn chứng cứ và volatility: [RFC 3227 §2](https://www.rfc-editor.org/rfc/rfc3227.html#section-2).
- Cú pháp và ý nghĩa `-readOnly` của Ghidra:
  [headless README chính thức](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/RuntimeScripts/support/analyzeHeadlessREADME.md).

## Truy vết catalog vào hướng dẫn

Mỗi hàng dưới đây bao gồm các subtask `.001–.003`; riêng **T1348 gồm `.001–.013`**. Tên file là dưới
`.claude/skills/soc-<đội>/reference/`. Đây là bản đồ nội dung đã đối chiếu với scenario/input/output của catalog,
**không phải kết quả chạy 175 task**, không phải chứng nhận dataset hoặc scorer.

<!-- catalog-coverage:start -->
| NICE | Đội | Reference chính | Quyết định/đầu ra phải hướng dẫn được |
|---|---|---|---|
| T1085 | MON | detection.md | Host đích bị dò, xếp hạng nguy cơ, liên kết chiến dịch, loại scanner có ngữ cảnh |
| T1112 | MON | alert-validation.md | Kiểm chứng claim, rule/tài sản thực, cửa sổ log bị chặn bởi cutoff |
| T1241 | MON | case-lifecycle.md | Trường bắt buộc, incident type/severity, đội xử lý theo SOP |
| T1242 | MON | case-lifecycle.md | Quyết định leo thang, tier, deadline đúng mốc |
| T1290 | MON | case-lifecycle.md | Thống kê alert/rule, đúng hạn, top noisy từ dữ liệu thô |
| T1299 | MON | cause-impact.md | Process khởi nguồn, t0, điều kiện khớp rule và nguyên nhân |
| T1347 | MON | detection.md | Request khai thác, correlation AD/web, claim có dẫn chứng |
| T1348 | MON | alert-groups.md | Masquerade, admin và 10 nhóm cảnh báo; tách hợp lệ/attempt/success/impact |
| T1349 | MON | case-lifecycle.md | Người nhận theo RASCI, kênh/hạn, đúng khách hàng |
| T1350 | MON | case-lifecycle.md | Log gap, hàng đợi ca và SLA cảnh báo quan trọng |
| T1351 | MON | cause-impact.md | Severity theo ô ma trận, scope và data risk |
| T1386 | MON | detection.md | Kênh C2, process, chu kỳ và phân vùng; loại nhiễu có căn cứ |
| T1387 | MON | alert-validation.md | Phiên/byte payload, NAT và severity của tài sản |
| T1388 | MON | containment.md | Lớp/hành động, bảo vệ VIP, RAM-first, tránh chặn dải được bảo vệ |
| T1389 | MON | containment.md | Gỡ tệp/persistence độc, giữ tệp sạch, kiểm trạng thái sau |
| T1428 | MON | case-lifecycle.md | Thông báo đúng đầu mối, đúng kênh, đúng hạn và nhất quán |
| T0020 | CNT | rule-authoring.md, engines.md | Rule đúng engine/technique, mẫu âm/dương, hiệu năng corpus |
| T1111 | CNT | rule-tuning.md | Bộ lọc FP, phân biệt lỗi logic/data/environment, giữ TP quan trọng |
| T1384 | CNT | coverage-intel.md | Rule bật + nguồn log khoẻ, gap theo intrusion set, hunt query/thiếu dữ liệu |
| T1406 | CNT | rule-authoring.md, engines.md | YARA/biến thể và mẫu sạch; PCAP thành signature hoặc parser có kiểm thử |
| T1644 | CNT | coverage-intel.md | IOC theo loại, nguồn/normalization, độ bền, rule TI chạy được |
| T0167 | HUNT | file-malware-hunt.md | Hash exact match, verdict từng tệp có căn cứ, family alias |
| T0292 | HUNT | exposure-review.md | Ưu tiên theo phơi nhiễm/tài sản/kiểm soát, bằng chứng khai thác lịch sử |
| T0845 | HUNT | ttp-actor.md | Mapping tactic/technique theo hành vi, dẫn chứng từng mục |
| T1053 | HUNT | ttp-actor.md | Cạnh lateral, persistence, chân dung xâm nhập theo dữ liệu |
| T1102 | HUNT | intrusion-analysis.md | Host bị xâm nhập hiện tại/quá khứ, phân biệt nhiễu hợp lệ |
| T1103 | HUNT | intrusion-analysis.md | Kill Chain, vector/timeline/scope; không ép chronology hay suy từ tên case |
| T1104 | HUNT | reporting.md | Báo cáo scope/timeline/root cause/IOC/persistence/remediation và locator |
| T1341 | HUNT | exposure-review.md | Cấu hình yếu và risk matrix; giữ trạng thái máy khi chỉ đọc |
| T1381 | HUNT | file-malware-hunt.md | Kết quả scan hash/family/scope, không cài/gỡ/cách ly ngoài quyền |
| T1487 | HUNT | file-malware-hunt.md | Tệp/persistence/process đang chạy, baseline, không sửa máy |
| T2012 | HUNT | exposure-review.md | Kết nối đầu xa, process, dấu hiệu C2/tunnel cả nội bộ |
| T2013 | HUNT | intrusion-analysis.md | IOC, anti-forensics, timeline; phân biệt log gap và bằng chứng xoá |
| T2016 | HUNT | intrusion-analysis.md | Host/account, mức kiểm soát/chạm/dò và căn cứ |
| T0173 | IR | reconstruction.md | UTC/offset, thứ tự sự kiện, các mốc thực sự có bằng chứng |
| T0182 | IR | malware-analysis.md | Tĩnh/động/RE; main/constants/key/C2/algorithm, verdict/family/IOC |
| T0397 | IR | evidence-forensics.md | Registry/Run/service/task/WMI, loại và vị trí persistence |
| T0510 | IR | triage-coordination.md | Severity/tier, IRT, artifact theo retention, SLA thu đúng mốc |
| T1090 | IR | network-attribution.md | Quy kết có căn cứ TTP/nguồn/alias hoặc không đủ căn cứ |
| T1109 | IR | containment-eradication.md | Gỡ webshell/backdoor/account trái phép, bảo toàn dịch vụ |
| T1250 | IR | triage-coordination.md | Triage tại t0, loại/mức và phản ứng ban đầu |
| T1251 | IR | containment-eradication.md | Kế hoạch theo phụ thuộc, từng backdoor có xử lý, rủi ro dịch vụ/chứng cứ |
| T1252 | IR | triage-coordination.md | Scope host/account/edge, mức khẩn cấp và căn cứ từng thực thể |
| T1253 | IR | evidence-forensics.md | Memory/injection, phân biệt JIT/relocation, kỹ thuật và IOC chỉ có trong RAM |
| T1257 | IR | containment-eradication.md | Thiếu nguồn/rule, tách khuyến nghị kỹ thuật/phát hiện/quy trình |
| T1315 | IR | triage-coordination.md | Hạn case, overdue và thứ tự theo severity/thời gian của SOP |
| T1316 | IR | triage-coordination.md | Hồ sơ bắt buộc/tùy chọn, thiếu gì mới cản đóng/phát hành |
| T1323 | IR | network-attribution.md | PCAP/IOC/C2, ba mức exfil, bytes có giới hạn quan sát |
| T1324 | IR | evidence-forensics.md | Thứ tự thu theo SOP, bảo toàn, hash và custody |
| T1332 | IR | reporting.md | Root cause, attack chain, impact và dẫn chứng |
| T1370 | IR | evidence-forensics.md | Thu bản sao không sửa bản gốc, volatility, anti-forensics |
| T1371 | IR | containment-eradication.md | IOC được chặn, lớp phù hợp, giữ hạ tầng hợp lệ và tránh chặn rộng |
| T1391 | IR | reconstruction.md | Patient Zero có căn cứ, cạnh lây nhiễm và giả thuyết khi thiếu log |
| T1607 | IR | evidence-forensics.md | AV cleanup thất bại thật, lịch sử và khoảng không đủ dữ liệu |
| T1617 | IR | reporting.md | Executive/Technical cùng facts, đủ mục bắt buộc và review |
<!-- catalog-coverage:end -->

T1253 giữ tên NICE gốc trong catalog nhưng scenario cụ thể ở repo yêu cầu phân tích memory/injection;
mapping theo scenario được đóng băng, không đổi nguồn để khớp tên handbook.

Ba skill phát triển đã được đọc riêng: `implement-task` giới hạn engineering task, `implement-benchmark-subtask`
giới hạn một ID catalog, `gate-review` review chỉ đọc và báo bằng chứng. Chúng không thay thế kỹ năng agent runtime;
giữ nguyên chính sách manual-only của `implement-task`/`gate-review`.

## Các tình huống phản chứng đã dùng để đọc lại nội dung

Đây là **review thủ công câu hướng dẫn**, chưa chạy Gemini. Cột cuối chỉ ra tài liệu hiện xử lý tình huống;
không gắn nhãn model PASS bằng cách kiểm vài từ khoá trong Markdown.

| Đầu vào phản chứng | Kết luận/hành vi cần có | Chỗ đã sửa |
|---|---|---|
| Request bị báo 403 nhưng có bản ghi backend thay đổi trái phép cùng correlation ID | Điều tra hiệu ứng; không phủ định chỉ từ status | MON alert-groups |
| HTTP 200 khi người dùng mở tài liệu được phép | Không gọi là xâm nhập vì status thành công | MON alert-groups; world contract |
| C2 có bằng chứng dùng IP 10.x trên 443 | Không loại khỏi hunt vì private IP/cổng quen | HUNT exposure; IR network |
| Tệp đã ký có hành vi độc; công cụ dev không ký dùng nhiều API nhạy cảm | Xét hành vi/nguồn, không gán nhãn từ chữ ký hoặc đếm API | HUNT file; IR malware |
| Hai URL `/Admin` và `/admin/` | Giữ hai quan sát gốc, không gộp bằng lower/strip toàn URL | CNT intel |
| AV chặn tệp trước thực thi; lần khác cùng hash tái xuất hiện trong quarantine | Không tự suy compromise hoặc cleanup thất bại | HUNT intrusion; IR evidence |
| Thiếu proxy log và không giải mã được TLS | Nêu giới hạn, không kết luận chắc chắn không exfil | IR network; case record |
| Timeline không có exfil/privilege escalation, timezone một nguồn chưa biết | Không tạo mốc/offset để đủ sáu pha | IR reconstruction |
| `tenant-a\\alice` và `tenant-b\\alice`, host khác domain cùng tên ngắn | Không gộp danh tính hoặc trộn dữ liệu tenant | IR reconstruction; HUNT TTP |
| Client đang đọc tài liệu trong lúc red kín đáo hành động | Tiếp công việc; chỉ đổi phản ứng theo lỗi/thông báo thực nhận | Client; world contract |
| DFIR tìm thấy dấu vết nhưng không có tool containment | Bàn giao evidence cho IR; không tự tuyên bố đã cô lập | IR SKILL; world contract |
| Đồng đội báo thành công nhưng không có kết quả hoặc ID hợp lệ | Xem như đầu mối, xác minh và ghi chưa biết | Lead; case record; red skills |
| Model trả `actions: []` sau khi đạt mục tiêu | Không tuyên bố runtime đã dừng; xác nhận fallback là giới hạn code | World contract |
| Không có Suricata/Ghidra trong menu | Báo chưa chạy/kiểm thử, không bịa output hoặc tự dựng công cụ | CNT engines; IR malware |

## Kiểm tra thực sự đã chạy

```powershell
.\.venv\Scripts\python.exe scripts/check_skills.py --out runs/skills-semantic-review/audit.json
.\.venv\Scripts\python.exe -m pytest -o addopts= tests/unit/test_skills.py tests/environments/test_bundle.py tests/unit/test_llm_solver.py -q
.\.venv\Scripts\python.exe scripts/validate_catalog.py
git diff --check
```

- Audit cấu trúc: 11 skills / 8 nghiệp vụ / 25 reference, tất cả role nạp được, không reference bị bỏ rơi.
- **38 tests passed**: loader/role/preflight, solver và bundle; prompt/ref xuất bundle khớp checkout.
- Mapping trong bảng được đối chiếu bằng ID với catalog: 55 nhóm, bao gồm 175 subtask; reference đích tồn tại.
- Frozen catalog validator: **PASS — 55 / 175 / 40 HV**; không thay đổi nguồn. Mapping đã kiểm lưu tại
  `runs/skills-semantic-review/coverage.json` cùng `audit.json`.
- Các kiểm tra này không đo chất lượng phán đoán model. Không chạy thêm smoke world cũ rồi gọi nó là đánh giá
  nghiệp vụ mới; không chạy VM/Docker hay Ghidra/IDA trong lượt này.
- Không đọc/in key pool và không gọi API model. Artifact audit local nằm trong `runs/skills-semantic-review/`;
  dữ liệu run không commit.

## Những phần vẫn chưa thể coi là hoàn tất

1. **Đánh giá hành vi model:** cần bộ case có chuyên gia gán nhãn, các phản chứng ở trên, đo độ đúng và bằng chứng
   qua nhiều lượt/seed; so sánh riêng scripted với LLM, ghi model/version/prompt/cost. Test loader không thay việc này.
2. **Năng lực môi trường:** browser/desktop, máy nạn nhân/OS, SIEM/SOAR/EDR/NSM, memory acquisition, Suricata/YARA native,
   Ghidra/IDA cần adapter, input, quyền và kiểm chứng thật. Tên công cụ trong skill không chứng minh đã tích hợp.
3. **Điều phối dài hạn:** scheduler hiện tick + scripted fallback; cần cơ chế nhiệm vụ/chiến dịch, hoàn tất/chờ,
   handoff acknowledgement, chống trùng tác động và lịch làm việc nếu muốn bảo đảm các hành vi đó bằng code.
4. **Phạm vi ngoài catalog:** cloud/IAM, email/browser thực, identity lifecycle, backup/restore toàn hệ thống và
   vận hành full SOC cần yêu cầu riêng và kịch bản kiểm chứng; không thể suy đủ từ 55 nhóm NICE này.
5. **Độ dài prompt:** case IR khoảng 63 nghìn ký tự, sát trần 64 nghìn; đây là giới hạn vận hành cần theo dõi,
   không được giải quyết bằng cắt âm thầm hoặc nâng trần không đánh giá token/cost/model context.

Các điểm trên là phần cần triển khai/đánh giá tiếp, không che bằng thêm danh sách tên công cụ vào SKILL.md.

## Checkpoint

- `4d4479b` — sửa kết luận SOC thiếu căn cứ, normalization, timeline và bảo toàn chứng cứ.
- `ca0f898` — công việc liên tục, bàn giao theo vai, phân biệt runtime và hướng dẫn, vòng đời rule/parser.
- Commit báo cáo này xem `git log --oneline -- docs/SKILLS_REVIEW_VI.md`; quy trình hoàn tác tại [ROLLBACK_VI](ROLLBACK_VI.md).
