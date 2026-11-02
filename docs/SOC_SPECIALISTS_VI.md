# Bổ sung chuyên môn và quy trình SOC

Phạm vi: nâng continuous application lab từ các vai tổng quát thành đội có chuyên môn,
có công cụ lấy chứng cứ, nhiệm vụ/bàn giao và trạng thái làm việc thực sự. Giữ cấu hình
cũ, catalog 175 subtask và dữ liệu run hiện có. Không coi tên skill là tích hợp sản phẩm.

## Các checkpoint triển khai

| Bước | Nội dung | Trạng thái |
|---|---|---|
| 1 | Query phân trang, cutoff/world scope, lấy evidence và case cũ, finding, đóng FP/mở lại | Đã có code và test HTTP |
| 2 | 12 chuyên môn blue, cấu hình agent kiêm nhiệm, nạp skill theo nhiệm vụ | Đã có registry, skill, phân quyền và test |
| 3 | Nhiệm vụ có nhận việc/bàn giao/kết quả, memory, wait và hoàn tất có hiệu lực | Đã kiểm HTTP, restart và plan trả về muộn |
| 4 | Artifact, kiểm rule, sức khoẻ telemetry và xác nhận phục hồi trong lab | Đã có công cụ và test HTTP/trạng thái |
| 5 | Agent-office, README, smoke đầu cuối và kiểm tra hồi quy | Đã qua 165 test Python, 9 test JS và các kiểm tra tĩnh |

## Chạy và quan sát

Từ root repo, tạo thư mục world mới (chọn tên khác nếu đường dẫn đã tồn tại):

```powershell
uv run saber world init --out runs/world-specialists --clients 4 --blue-specialists
uv run saber world run --out runs/world-specialists --ticks 30
node agent-office/bin/agent-office.js watch --world runs/world-specialists --open
```

Tiếp tục dài hạn bằng `world run --out runs/world-specialists --forever`; dừng từ terminal
khác bằng `world stop --out runs/world-specialists`. Sau STOP cần thêm `--resume` khi chạy lại.
Các lệnh trên mặc định scripted, không đọc key. Muốn planner Gemini dùng hướng dẫn budget/pool
trong [CONTINUOUS_WORLD_VI](CONTINUOUS_WORLD_VI.md); lượt bổ sung này không gọi API thật.

Với environment profiles, cấu hình actor ở `world.actors` của environment JSON trước khi
render/chạy lần đầu; cùng schema `role`/`specialties`. Bundle cũ cần render/rebuild từ source
mới. Không tự chuyển roster của world đã có: tạo world mới nếu muốn thay danh tính/chuyên môn.

Office hiển thị chuyên môn đã cấp, chuyên môn/task ACTIVE, số task theo trạng thái,
WAITING và tick thức dậy, DONE. Notebook, nội dung task và lý do kết thúc không được đưa
lên snapshot. Viewer dùng snapshot cũ vẫn tương thích.

## Chứng cứ và case

Blue dùng `query_events` với `world_id`, `as_of_tick`, bộ lọc và `after_id`; kết quả theo
thứ tự tăng dần, có cursor và cờ giới hạn retention. Không có SQL tùy ý hoặc quyền đọc
sealed archive. `get_evidence` lấy event còn giữ hoặc bản sao đã gắn vào case.

`get_case` lấy case ngoài cửa sổ observation. `append_evidence` giữ dữ liệu cũ và thêm
event có thật; `record_finding` ghi claim/citation/severity/việc tiếp theo. Các cập nhật
cần `expected_revision` để tránh ghi đè quyết định mới hơn. Finding là kết luận analyst,
không thay ground truth của evaluator. Lead có thể đóng FP có dẫn chứng và mở lại case;
case có tác động vẫn phải qua kiểm chứng phản ứng khi đóng theo trạng thái resolved.
Thêm evidence mới giữ lịch sử findings nhưng đưa classification về UNDETERMINED, yêu cầu
đánh giá lại trước khi đóng FP. Kiểm recovery là công cụ hỗ trợ quyết định; hiện không phải
điều kiện bắt buộc bổ sung của API đóng resolved, vốn kiểm phản ứng và mitigation.

Quyền giới hạn trong một world được xác thực bởi HTTP capability. Một world hiện là một
lab dùng chung; đây chưa phải giải pháp SOC nhiều khách hàng có phân quyền tenant riêng.

## Chuyên môn

Blue có 12 chuyên môn: `lead`, `monitor`, `hunter`, `dfir`, `ir`, `content`, `malware`,
`network`, `intel`, `platform`, `identity`, `recovery`. Sáu vai mặc định giữ nguyên;
DFIR dùng `soc-dfir` riêng. Bảy skill mới đưa tổng repo lên 18 skills (15 nghiệp vụ,
3 phát triển), vẫn dùng 25 reference có sẵn để không sao chép handbook.
Catalog benchmark giữ bốn nhóm NICE `MON/CNT/HUNT/IR` với 175 subtask; 12 chuyên môn
ở đây là roster của continuous world. Không đổi schema/catalog benchmark để tăng số vai.

| Role | Skill | Công cụ riêng nổi bật ngoài query/case/task/notebook chung |
|---|---|---|
| `lead` | `soc-orchestrator` | create/cancel task, assign, close/reopen case, resume blue, notify, verify_recovery |
| `monitor` | `soc-mon` | open_case |
| `hunter` | `soc-hunt` | open_case |
| `dfir` | `soc-dfir` | investigate, capture/read/analyze artifact |
| `ir` | `soc-ir` | contain/release, quarantine/unquarantine, restore, notify, verify_recovery |
| `content` | `soc-cnt` | patch, test/publish/rollback rule; deploy_rule legacy |
| `malware` | `soc-malware` | capture/read/analyze artifact |
| `network` | `soc-network` | investigate, capture/read/analyze artifact |
| `intel` | `soc-intel` | capture/read/analyze artifact |
| `platform` | `soc-platform` | telemetry_health (mọi blue đều có), query/finding về sức khỏe nguồn |
| `identity` | `soc-identity` | investigate, capture/read/analyze artifact |
| `recovery` | `soc-recovery` | verify_recovery |

Operator cấu hình kiêm nhiệm trong world config, ví dụ:

```json
{"id":"blue-analyst","team":"blue","role":"dfir","specialties":["network","malware"]}
```

Tool của actor là hợp quyền của các chuyên môn được cấu hình. Message/model không tự
thêm chuyên môn hay quyền. Skill đang dùng chuyển theo chuyên môn nhiệm vụ trong phạm
vi đó; toàn bộ skill đã cấu hình được preflight trước khi mở lab có model.

Baseline scripted nhận task được giao và dùng chuyên môn ACTIVE; DFIR/network/identity
thu timeline, malware/intel thu/phân tích metadata artifact, platform kiểm telemetry,
recovery kiểm phục hồi. Nó không tự giải quyết mọi mục tiêu free-text, không tự lập
chiến dịch hay đóng task bằng kết luận giả. Planner/operator dùng công cụ để đánh giá,
ghi finding và complete/block/handoff theo chứng cứ. Task DONE là lời báo cáo có citation,
không phải chứng nhận độc lập rằng phán đoán analyst đúng.

## Nhiệm vụ và vòng đời actor

Lead tạo task theo chuyên môn; bên nhận phải accept, chỉ có một task ACTIVE tại một
thời điểm. Kết quả cần dẫn chứng đã gắn vào case. Handoff đưa việc về OFFERED và bên
nhận phải chấp nhận; blocked có lý do, lead có thể cancel và giao việc thay thế. Deadline
là tick của lab, không được tự chuyển thành SLA phút của khách hàng.

Notebook riêng tồn tại qua restart, có 200 mục/actor, phân trang và báo đầy rõ ràng;
không bị ghi đè bởi note 1.000 ký tự của planner. Notebook không hiện trong office/team.

`wait` tạm ngừng actor theo tick; `finish` dừng tới khi resume. Plan rỗng hợp lệ được
chuyển thành wait một tick. Model lỗi hoặc plan sai vẫn có fallback. In-flight plan
mang generation của actor: đổi nhiệm vụ/trạng thái sẽ vô hiệu hóa quyết định cũ.

Lead được resume đồng đội blue. Operator có thể resume bất kỳ actor trong world đã dừng:

```powershell
uv run saber world actor-resume --out runs/world --actor red-impact
```

## Công cụ chuyên môn chạy được

- `capture_artifact` chụp event/document/job/identity/service trong phạm vi case; lưu
  SHA-256, byte count, nguồn, người thu và tick. Bản chụp bất biến dù tài liệu sống thay
  đổi. `read_artifact` phân trang; sai hash thì từ chối. Không có đường dẫn host tùy ý.
- `analyze_artifact` builtin tính hash/size và trích URL từ JSON lab. Kết quả ghi rõ
  chưa đánh giá malware, không phải decompile hay sandbox execution. Yêu cầu native
  Ghidra/IDA/Volatility/tshark/YARA/Suricata trả lỗi adapter chưa cấu hình, không tạo
  báo cáo giả. Cần adapter và input thực được cấp để hoàn thành phần tích hợp đó.
- `test_rule` chạy điều kiện engine `application-v1` trên event dương/âm được dẫn ID;
  trả TP/FP/FN/TN theo nhãn người gọi. Không đọc gold. `publish_rule` đòi kết quả test
  không FP/FN trên corpus đó và expected_version; rule mới áp vào telemetry thực.
  `rollback_rule` khôi phục bản cũ thành version mới, giữ lịch sử. Không tự deploy SIEM ngoài.
- `telemetry_health` báo range/retention, số event và lỗi theo loại hành động, trạng thái
  adapter. Không có baseline thì không tự kết luận nguồn im lặng là mất log.
- `verify_recovery` kiểm dịch vụ, hiệu lực giảm thiểu, client bị hạn chế và công việc
  sau phản ứng của từng client bị ảnh hưởng. Chỉ một client phục hồi chưa đủ cho outage
  ảnh hưởng nhiều client. Tính toàn vẹn dữ liệu ghi `not_measured` khi thiếu baseline/backup.

Mọi kết quả là trong application lab. Không gọi API Gemini hoặc native engine trong
các test offline này; không có chứng nhận benchmark/chất lượng model từ test công cụ.

## Kiểm chứng ngày 2026-11-01

- **165 test Python qua**: world, loader/solver, population và environment profiles.
  Hai test `tests/world/test_soc_workflow.py` kiểm luồng HTTP có điều phối theo kịch bản
  và smoke scripted 17 actor (2 client, 3 red, 12 blue) trong 12 tick; kiểm CLI resume
  từ chối writer đang chạy và giữ dữ liệu. Test kịch bản chọn hành động sẵn, không đánh giá
  khả năng model tự lập kế hoạch hay tự nhận diện đúng sự cố.
- **9 test JavaScript qua**, viewer build thành công; kiểm trạng thái actor và tương thích
  snapshot. Không có notebook/task text bị xuất lên office.
- Audit **PASS: 18 skills / 15 nghiệp vụ / 25 reference**, không thiếu file/link/role;
  prompt trong giới hạn. Ruff lint/format, mypy (158 source files), frozen catalog
  (**55 nhóm / 175 subtask / 40 HV**) đều qua.
- Artifact local: `runs/soc-specialists/audit.json`, `runs/soc-specialists/regression.xml`.
  Không đưa dữ liệu run vào Git. Không triển khai Docker/VM, SIEM/SOAR/EDR hay native
  malware engine trong lượt kiểm chứng này. Trạng thái vẫn `DEV_SIMULATION_ONLY`.

Tái lập từ root repo:

```powershell
uv run pytest -o addopts= tests/world tests/unit/test_skills.py tests/unit/test_llm_solver.py tests/environments tests/population -q
uv run python scripts/check_skills.py --out runs/soc-specialists/audit.json
uv run ruff check src tests scripts
uv run ruff format --check src tests
uv run mypy
uv run python scripts/validate_catalog.py
npm --prefix agent-office test
npm --prefix agent-office run build:viewer
```

Checkpoint code đã push liên tục: `c49a109` evidence/case, `9cabb54` skills/roles,
`2997ba4` tasks/notebook/lifecycle, `dafe196` artifact/rule/recovery, `2786a5f` vô hiệu
kết luận cũ khi thêm evidence, `266219f` office/baseline, `a268bc1` workflow test và
hợp đồng chuyên môn. Xem [ROLLBACK_VI](ROLLBACK_VI.md) để quay lại từng bước.
