# Implementation sequence — Claude Code lấy 175 subtask làm đơn vị benchmark

T001–T038 trong `tasks/BACKLOG.md` là engineering backlog cũ. **Không đổi tên T001 thành T1112.001.** Đây là hai namespace khác nhau. Nguyên tắc cho mỗi PR nghiệp vụ: đúng **một** `T####.NNN`; những module dùng chung phát triển bằng engineering PR riêng.

## Track kiến trúc song song

- **Foundation**: engineering T001–T005 (repo, DTO, store, API, policy) + chuẩn `catalog/subtasks.json`, artifacts, scores.
- **Offline engine**: engineering T006–T014 (fixtures, normalization, replay, grader, reports).
- **Range/SOC integration**: T015–T024 (lab, snapshots, capture, approved emulation, SIEM adapter) chỉ chạy thật sau khi isolation được duyệt.
- **Agents/Evaluation**: T025–T038 (agents, bounded tools, baselines, eval), nhưng first working baseline cần xuất hiện sớm trong offline vertical slice.

## Wave 0 — đọc đúng nguồn, dựng catalog (PR bridge B001–B005)

| PR bridge | Phải code | Mốc nghiệm thu |
|---|---|---|
| B001 Source importer | Source parser chỉ parse JSON, freeze hash, 55 NICE/175 subtask/HV-01…HV-40 | `python scripts/validate_catalog.py` PASS; mọi subtask có duy nhất task/service |
| B002 Typed SubtaskSpec | Pydantic models, output schema registry, validation cho `file/soc/vm` | invalid env/ID/weight rejected, source immutable |
| B003 Grader library | enum, set/Fβ, numeric, Kendall, gates, cite, state diff, exec sandbox | unit/golden + boundary tests; không dùng eval nguồn |
| B004 Episode builder | private truth/public manifest, fixtures, seed, hash, deadline | Agent-visible payload không lộ labels; same seed deterministic |
| B005 Subtask runner/CLI | `saber task list/show/build/run/grade/report` interface | metadata → build → run → grade → report chạy với fake adapter |

Không đánh đồng `B001` hoàn thành với 175 benchmark subtasks đã chạy.

## Wave 1 — một vertical slice FILE cho từng dịch vụ

| Sequence | Subtask | Deliverable chạy thật của module |
|---|---|---|
| 1 | `T1112.001` MON | một alert HV-01 → JSON `verdict`, sealed label grader TP/FP |
| 2 | `T1348.001` MON | nhiều process HV-15 → `masquerading[]`, false positives |
| 3 | `T2012.001` HUNT | netstat HV-17 → set abnormal (ip,port), graded |
| 4 | `T0020.001` CNT | log HV-02 → agent viết rule, chạy verifier offline trong sandbox với timeout |
| 5 | `T0173.001` IR | 30 sự kiện 3 múi giờ → normalized order/Kendall tau |

**Go/no-go:** ít nhất 5 subtask có fixture tạo thực sự, hidden GT, type checking, scorer edge cases và run report; không chỉ in prompt mock.

## Wave 2 — tăng độ khó FILE + SOC read-only

- Mở phiên bản `*.002` cho 5 task ở Wave 1, có hard negatives.
- `T1112.003`, `T1299.003`, `T1348.003`: case có nhiều HV sources và time-guarded queries; sử dụng SOAR/SIEM sandbox và dataset verified.
- `T1348.004–.013`: **10 chuyên nhóm alert**, mỗi nhóm một manifest riêng, không sao chép blindly nhãn TP/FP chung.
- `T0020.002/.003`, `T1111.003`, `T1406.003`: rule compile và chạy held-out corpus/PCAP; đánh giá FP và coverage.
- `T1386.003`, `T0173.003`, `T1252.003`: multi-source correlation, timeline và asset scope.

**Go/no-go:** không có cross-tenant/future-log leakage; output schema từng bài; các hard gates làm điểm 0/cap đúng như source. Các backend thật chỉ có thể nhận VERIFIED_INTEGRATION khi nguồn/tool khả dụng.

## Wave 3 — VM / trạng thái (cần isolation proof + approval)

- **Observation read-only**: `T1487.001→.003` (file/persistence/process), `T2012.003` (netconn), `T1341.003` (misconfiguration), `T1381.002/.003` (scan with no guest changes), `T1102.003` (multi-host search).
- **Forensic acquisition**: `T1370.001→.003` (hash, mtime, order of volatility), `T0397.003` (registry/WMI).
- **Stateful defensive response**: `T1389.001→.003`, `T1109.001→.003` và `T1388.003` (các gate bảo toàn bằng chứng, VIP, critical asset, service health).

Chia read-only và state-mutating thành **hai tool permission profiles khác nhau**. Verifier phải chạy ngoài guest. Không chấm bằng lời hứa đã xóa/cô lập nếu trạng thái thật không thay đổi.

## Wave 4 — toàn bộ coverage theo service

- `MON`: 16 NICE / 58 subtask. Gồm triage, correlation, severity, SLA, ticket, thông báo, containment.
- `CNT`: 5 NICE / 15 subtask. Gồm rule viết mới, tuning, mapping, parser/signature, TI→content.
- `HUNT`: 13 NICE / 39 subtask. Gồm process, persistence, file, memory, outbound C2, IOC, scope, hypothesis/CA.
- `IR`: 21 NICE / 63 subtask. Gồm forensic, chain/timeline, collection, eradication, response activation, recovery và báo cáo.

Mỗi subtask chỉ chuyển READY khi đã có sample nguồn/approved synthetic, nhãn ground truth độc lập, scorer, golden tests, versioned artifacts và reviewer signoff. Theo dõi độc lập: `SPECIFIED`, `DATA_BLOCKED`, `SCORER_BLOCKED`, `IMPLEMENTED_DEV`, `VALIDATED_LAB`, `READY_BENCHMARK`.

## Wave 5 — multi-agent experiment

Sau khi các subtask sở hữu runner, so sánh rules-only, single agent và multi agent trên **cùng episodes và tool budget**. Không được lấy 175 định nghĩa rồi coi đó là 175 lần chạy thống kê độc lập. Split theo family/host/campaign, có benign-hard-negative và attacker success checks. Report cả per-task/per-service/per-env, safety violations, cost và invalid rate.

## Phụ thuộc dữ liệu bắt buộc trước khi gọi tích hợp thật

- Dữ liệu VCS/SOAR/SIEM/viettel scanner có quyền sử dụng và kế hoạch vô danh hoá.
- Host/image mạng lab cô lập, owner đồng ý; inventory và snapshot ready.
- Một bộ reference outputs + independent private labels + grader acceptance vectors cho subtask ưu tiên.
- Đặc tả vai trò và API của SIEM, SOAR, EDR, product adapters (các tên hãng trong source **không phải** bằng chứng có quyền/API thực tế).
- Chốt đặc tả công thức nguồn có chỗ không xác định trên tập rỗng và cách phân biệt LLM answer với action/state.

## Một PR subtask cần review gì?

Ví dụ `T1112.001`: path `src/saber/subtasks/t1112_001` và test `tests/subtasks/test_t1112_001.py`. Review phải chứng minh: input HV-01, output DTO chính xác `verdict`, labels kín, âm/dương, invalid không tính nhầm FN, scorer exact, run report có hash. Không cần provision Proxmox cho bài `file` này.
