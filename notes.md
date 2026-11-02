# Notes — các lệnh chạy SABER

Cập nhật: 2026-11-02. Dùng để tra lệnh vận hành client / red team / blue team.
Các ví dụ chạy trong PowerShell; chọn chế độ cần dùng, không chạy toàn bộ file như script.

| Muốn làm gì | Xem mục |
|---|---|
| Tạo world, chỉnh số agents | 1–2 |
| Chạy thử hoặc chạy liên tục với Gemini | 3 |
| Xem Agent Office, log, báo cáo | 4 |
| Dừng và tiếp tục | 5 |
| Xem bài học, kiểm thử và rollback skill | 6 |
| Test API Gemini thật | 7 |
| Chạy Docker sandbox | 8 |
| Chạy VM hoặc server riêng | 9 |
| Kiểm tra skills, catalog và viewer | 10 |

## 1. Chuẩn bị

Terminal tại root repo, Python 3.12+ và uv. Node.js 18+ cần cho Agent Office;
Docker Linux engine + Compose chỉ cần khi dùng sandbox.

```powershell
cd E:\Project\Saber-bench
uv sync --locked
```

Nếu repo ở máy khác, thay đường dẫn `cd`. Với virtualenv đã có, có thể thay
`uv run saber` bằng `.\.venv\Scripts\python.exe -m saber.cli.main`.

Các đường dẫn `runs/my-world`, `runs/env-sandbox.json`… là ví dụ. Dùng đường dẫn
nhất quán trong cùng một luồng; tạo world/bundle mới bằng đường dẫn chưa tồn tại.
Mỗi world chỉ chạy một process ghi dữ liệu tại một thời điểm.

## 2. Tạo world và chỉnh số agents

Ví dụ **20 clients + 3 red + 12 blue = 35 agents**:

```powershell
uv run saber world init --out runs/my-world --clients 20 --blue-specialists
notepad runs/my-world/config.json
```

- `--clients`: 1–100 client khi dùng lệnh init; mặc định `world init` là 6.
- Red mặc định 3 agent với role `recon`, `access`, `impact`.
- Blue mặc định 6 agent; `--blue-specialists` tạo đủ 12 chuyên môn.
- Chưa có cờ `--red N` / `--blue N`. Thêm/bớt object trong `actors` để chỉnh số lượng.
- Mỗi object là một agent, `id` phải khác nhau; có thể nhiều agent cùng role.
- Blue roles: `lead`, `monitor`, `hunter`, `dfir`, `ir`, `content`, `malware`,
  `network`, `intel`, `platform`, `identity`, `recovery`.
- Tổng tối đa 200 agents/world. Sửa roster **trước lần chạy đầu**; world đã chạy
  giữ nguyên cấu hình, muốn thay roster thì tạo world mới.

Ví dụ object có thể thêm vào mảng `actors` (giữ đúng dấu phẩy của JSON):

```json
{
  "id": "blue-dfir-2",
  "team": "blue",
  "role": "dfir",
  "goal": "Investigate incidents using cited evidence."
}
```

Với các profile `env`, chỉnh **`world.actors` trong environment JSON** trước khi
render/chạy lần đầu. `env init` mặc định 4 clients + 3 red + 6 blue và chưa có cờ
`--blue-specialists`; có thể thêm chuyên môn trực tiếp trong `world.actors`.

## 3. Chạy local

Chọn **một** chế độ; chạy xong/dừng process cũ trước khi dùng chế độ khác trên cùng world.

### Scripted — không gọi Gemini

Chạy thêm 60 tick rồi dừng:

```powershell
uv run saber world run --out runs/my-world --ticks 60
```

Chạy liên tục:

```powershell
uv run saber world run --out runs/my-world --forever
```

### Gemini thật — hybrid, có scripted fallback

Chạy thử 60 tick:

```powershell
uv run saber world run --out runs/my-world --ticks 60 --llm --key-pool keys_pool.txt --call-budget 200
```

Chạy liên tục, supervisor khởi động lại khi process lỗi, tối đa 3 lần:

```powershell
uv run saber world supervise --out runs/my-world --llm --key-pool keys_pool.txt --call-budget 200
```

- Model mặc định `gemini-3.5-flash-lite`; đổi bằng `--model TEN_MODEL`.
- Keys được chương trình nạp từ file; không chép giá trị key vào notes/config/Git.
- Pool mặc định theo thứ tự sau loại trùng: client 1–200, red 201–400, blue phần còn lại.
  Keys chuyển trong đúng đội; số keys không phải số agents.
- `--call-budget 200` là trần **HTTP attempts tích lũy của world**, gồm retry,
  planning, reflection và replay. Restart không reset. Đây không phải trần tiền.
- Hết budget hoặc model lỗi, scripted fallback có thể tiếp tục. `--forever` không
  đồng nghĩa Gemini có quota vô hạn. Xem nguồn hành động và `llm.successes` để phân biệt.
- Supervisor chạy foreground trong terminal; chưa phải Windows service tự bật cùng máy.

## 4. Xem hoạt động — dùng terminal riêng

Agent Office (có thể xem world đang chạy hoặc đã dừng):

```powershell
node agent-office/bin/agent-office.js watch --world runs/my-world --open
```

URL được in ra, thường là `http://127.0.0.1:7788`. Viewer hiển thị từng đội, role/task,
tool cuối, HTTP status, nguồn `llm` / `scripted` / `scripted-fallback`, usage và counters
học. Viewer chỉ đọc snapshot, không khởi động agents hay gọi model; hoạt ảnh 3D minh họa.

**Bố cục và số slots:** Clients, Red Team, Blue Team có khu riêng. Trong sidebar,
chọn **Số bàn mỗi đội → 12 hoặc 24**, tương ứng tối đa **36 hoặc 72 agents/lượt xem**.
Mũi tên trang chuyển nhóm tiếp theo của từng đội; vẫn xem đủ roster tối đa 200 agents.
Các nút **Toàn cảnh / Clients / Red Team / Blue Team** phía trên đổi góc nhìn camera;
bộ lọc đội trong sidebar còn giới hạn agent đang hiển thị. Thêm slots chỉ đổi viewer,
không tăng số agents, số worker hay quota. Sau khi cập nhật code, refresh trình duyệt
bằng Ctrl+F5 để nạp viewer mới.

**Xem cụ thể red tấn công / blue phản ứng:** lọc Red Team, bấm robot, màn hình/bàn
hoặc thẻ `red-access` / `red-impact`. Bảng chi tiết có timeline; bấm một event để xem
agent → công cụ → mục tiêu → HTTP status, nguồn `llm`/scripted và case liên quan.
Phần dưới hiển thị phản ứng blue có bằng chứng. Escape/nút Đóng để quay lại;
checkbox cho phép chỉ xem thao tác của agent hoặc kèm sự kiện liên quan.

Demo scripted đã chuẩn bị trên máy này, có thể xem ngay mà không gọi Gemini:

```powershell
node agent-office/bin/agent-office.js watch --world runs/office-inspector-demo --open
```

Nếu máy khác chưa có demo, tạo một world mới theo mục 2 và chạy ít nhất 18 tick.
Hướng dẫn từng bước: [chi tiết Agent Office](agent-office/README.md).

Xem báo cáo mới nhất:

```powershell
uv run saber world status --out runs/my-world
```

Theo dõi log liên tục trong terminal riêng; Ctrl+C dừng việc xem log:

```powershell
Get-Content runs/my-world/access.jsonl -Tail 30 -Wait
```

| File trong world | Nội dung |
|---|---|
| `config.json` | Roster và cấu hình |
| `report.json` | Kết quả, tác động, counters và usage provider |
| `office.json` | Snapshot cho Agent Office |
| `learning.json` | Counters, trạng thái học và phiên bản |
| `access.jsonl` | Log thao tác; có rotation sang `.1`–`.3` |
| `world.sqlite3` | Trạng thái, case, journal và dữ liệu đánh giá |
| `STOP` | Yêu cầu dừng; tiếp tục bằng `--resume` |

Trong runtime world thông thường, log được xuất sau tick. Smoke learning gọi trực tiếp
các bước kiểm thử nên xem `live-learning-check.json` của script để biết hành động đã chạy.
Office có timeline theo agent/case trong cửa sổ tối đa 200 event gần nhất toàn world,
12 case, 50 evidence IDs trong cửa sổ/case và 8 phản ứng cuối/case; không phải toàn bộ
lịch sử. Snapshot cũ báo chưa có trace: chạy/resume bằng code mới để xuất dữ liệu.
HTTP thành công không tự chứng minh tấn công thành công. Đây là thao tác trong lab,
chưa phải video desktop/terminal của máy riêng.

## 5. Dừng, tiếp tục và resume actor

Yêu cầu dừng world từ terminal khác, giữ dữ liệu:

```powershell
uv run saber world stop --out runs/my-world
```

Đợi process báo dừng/thoát rồi chạy tiếp với Gemini:

```powershell
uv run saber world supervise --out runs/my-world --resume --llm --key-pool keys_pool.txt --call-budget 200
```

Hoặc tiếp tục scripted:

```powershell
uv run saber world run --out runs/my-world --resume --forever
```

Nếu một actor tự `finish`, resume riêng actor khi world đã dừng, rồi chạy lại world:

```powershell
uv run saber world actor-resume --out runs/my-world --actor ACTOR_ID
```

Thay `ACTOR_ID` bằng ID trong config. Resume world không tự bật lại actor đã finish.
Các counters API vẫn tích lũy; không xóa dữ liệu để coi quota đã được phục hồi.

## 6. Theo dõi và quản lý việc học

Xem counters khi world đang chạy hoặc đã dừng:

```powershell
uv run saber world learning status --out runs/my-world
```

Các lệnh còn lại trong mục này dùng với **world đã chạy ít nhất một lượt và hiện
đã dừng**. Reflection cần Gemini; phát hành cần replay suite phù hợp và vượt gate.
Có thể trả `NO_LESSON` hoặc từ chối proposal; không bảo đảm mỗi lượt sẽ có skill mới.

Cài suite mẫu cho skill client:

```powershell
uv run saber world learning install-suite --out runs/my-world --file config/learning/client-session.json
```

Mẫu này chỉ kiểm skill client, không tự bao phủ các skill red/blue. Suite phải do
operator chuẩn bị; agents không tự sửa đáp án kiểm thử.

Liệt kê và xem chi tiết:

```powershell
uv run saber world learning list --out runs/my-world
uv run saber world learning inspect --out runs/my-world --proposal PROPOSAL_ID
uv run saber world learning versions --out runs/my-world --skill client-user
```

Chỉ xử lý tối đa 4 công việc học đang chờ, có gọi API thật, không tiến tick của actors:

```powershell
uv run saber world run --out runs/my-world --learning-only --learning-jobs 4 --llm --key-pool keys_pool.txt --call-budget 200
```

Budget vẫn tích lũy, STOP được giữ nguyên; một job có thể dùng nhiều HTTP attempts.
Đọc status sau khi chạy vì công việc có thể còn chờ hoặc bị deferred.

Xuất đề xuất ra Markdown, retry một công việc DEFERRED, hoặc rollback skill:

```powershell
uv run saber world learning export --out runs/my-world --proposal PROPOSAL_ID --file runs/review/lesson-01.md
uv run saber world learning retry --out runs/my-world --kind episode --id EPISODE_ID
uv run saber world learning rollback --out runs/my-world --skill client-user --version VERSION_ID
```

Thay các ID bằng kết quả thật từ `list` / `versions`. Retry evaluation dùng
`--kind proposal --id PROPOSAL_ID`. Export từ chối ghi đè file. Rollback chọn bản đã
phát hành cho epoch an toàn tiếp theo; case đang mở giữ phiên bản đã pin.
Các thao tác này không tự sửa file skill trong repo hay commit Git.

## 7. Các script test Gemini thật

Các lệnh có `--live` dưới đây thực sự dùng API. Mỗi script tạo world riêng gồm
**1 client + 1 red + 1 blue**; thư mục đầu ra ban đầu phải mới.

### API, hành động, restart và chuyển key

```powershell
uv run python scripts/smoke_world_gemini.py --live --out runs/check-gemini-01 --call-budget 12
```

Mặc định 2 vòng; budget tối đa 12 attempts. Script dùng giới hạn cục bộ 1 call/key/ngày
để kiểm chuyển key, không phải cố làm cạn quota Google. Kết quả: `live-check.json`.

### Planning, thực thi, reflection và replay

```powershell
uv run python scripts/smoke_learning_gemini.py --live --out runs/check-learning-01 --call-budget 24
```

Budget tối đa 24 attempts. Kết quả: `live-learning-check.json`. Script có thể exit 1
khi model trả `NO_LESSON`, chưa hoàn thành luồng tự sinh đề xuất/replay; xem receipt
để phân biệt với lỗi gọi API.

Nếu cần kiểm riêng replay bằng đề xuất của bộ test:

```powershell
uv run python scripts/smoke_learning_gemini.py --live --resume-probe --out runs/check-learning-01 --call-budget 24
```

Probe dùng đúng world/model/budget ban đầu, không chạy lại planning/reflection và
không được lặp trên cùng receipt. Đề xuất có nguồn `operator_smoke_probe`; không
gán nó cho Gemini. Probe hoàn thành/exit 0 không đồng nghĩa candidate được chấp nhận.

## 8. Sandbox Docker — lựa chọn thay cho local

Docker Linux engine và Compose cần hoạt động. Tạo cấu hình mới, chỉnh `world.actors`
nếu cần, rồi kiểm tra và render bundle:

```powershell
uv run saber env init --profile sandbox --name my-sandbox --clients 20 --out runs/env-sandbox.json
notepad runs/env-sandbox.json
uv run saber env validate --config runs/env-sandbox.json
uv run saber env doctor --config runs/env-sandbox.json
uv run saber env render --config runs/env-sandbox.json --out runs/bundle-sandbox
```

Chọn **một** lệnh bật. Scripted:

```powershell
uv run saber env up --bundle runs/bundle-sandbox
```

Hoặc Gemini thật:

```powershell
uv run saber env up --bundle runs/bundle-sandbox --llm --key-pool keys_pool.txt --call-budget 200
```

Scripted mặc định không có mạng ngoài. Chế độ Gemini bật outbound cho controller,
mount key chỉ đọc, không chép key vào image/bundle; egress chưa lọc theo domain.

Kiểm tra container và xuất report trước khi down; dùng tên file report mới mỗi lần:

```powershell
uv run saber env status --bundle runs/bundle-sandbox
uv run saber env report --bundle runs/bundle-sandbox --out runs/sandbox-report-01.json
```

Viewer tại Docker host, trong terminal riêng:

```powershell
node agent-office/bin/agent-office.js watch --bundle runs/bundle-sandbox --open
```

Dừng và giữ named volume:

```powershell
uv run saber env down --bundle runs/bundle-sandbox
```

Tiếp tục Gemini sau khi dừng:

```powershell
uv run saber env up --bundle runs/bundle-sandbox --resume --llm --key-pool keys_pool.txt --call-budget 200
```

World nằm trong `/data` của volume, không phải thư mục bundle trên host. Bundle mới
có dữ liệu riêng; render mới không tự chuyển dữ liệu cũ. Chi tiết:
[ENVIRONMENTS_VI](docs/ENVIRONMENTS_VI.md).

## 9. VM hoặc server riêng

### Chuẩn bị bundle trên máy hiện tại

VM do người dùng tự dựng. Tạo config, chỉnh `world.actors` trước khi render:

```powershell
uv run saber env init --profile vm --name my-vm --clients 20 --out runs/env-vm.json
notepad runs/env-vm.json
uv run saber env render --config runs/env-vm.json --out runs/bundle-vm
```

Với server riêng, thay profile bằng `remote`, chọn tên config/bundle tương ứng rồi
chuyển bundle sang server. SABER không tự tạo VM hay SSH vào máy đích.

### Chạy trong guest/server, tại thư mục `bundle-vm/source`

```powershell
uv sync --frozen --no-dev
uv run --no-sync saber env doctor --config ../environment.json
```

Chọn scripted:

```powershell
uv run --no-sync saber env run --config ../environment.json --out ../world --forever --on-target
```

Hoặc Gemini, thay `PATH_TRONG_GUEST` bằng đường dẫn key pool thực tế trên máy đích:

```powershell
uv run --no-sync saber env run --config ../environment.json --out ../world --forever --on-target --llm --key-pool PATH_TRONG_GUEST --call-budget 200
```

Từ terminal thứ hai trong cùng thư mục `source`:

```powershell
uv run --no-sync saber world status --out ../world
uv run --no-sync saber world stop --out ../world
```

Sau khi dừng, thêm `--resume` vào lệnh `env run` đã chọn để tiếp tục. `--on-target`
xác nhận terminal đang ở máy đích; không phải lệnh kết nối máy từ xa.

Nếu guest/server có Node.js, mở viewer từ thư mục **gốc bundle** trong terminal khác:

```powershell
node agent-office/bin/agent-office.js watch --world world --open
```

Local, sandbox, VM và remote đều chạy cùng application lab; mỗi actor chưa có
desktop/VM riêng. Profile không tự cài hoặc kết nối SIEM/SOAR/Ghidra/IDA.

## 10. Kiểm tra và công cụ hỗ trợ

Các lệnh dưới đây chạy ở root repo:

```powershell
# Kiểm tra skills và frozen catalog, không gọi model
uv run python scripts/check_skills.py
uv run python scripts/validate_catalog.py

# Xem một subtask và tiến độ triển khai
uv run python scripts/show_subtask.py T1112.001
uv run python scripts/ledger.py summary

# Kiểm thử offline của world và harness learning
uv run pytest -o addopts= tests/world -q

# Kiểm thử viewer, không gọi model
npm --prefix agent-office test
```

Chỉ khi sửa source viewer: dùng dependencies hiện có; nếu thiếu, cài từ lockfile
rồi build và commit cả source lẫn viewer đã build:

```powershell
npm --prefix agent-office ci
npm --prefix agent-office run build:viewer
```

`scripts/run_autonomous.py` là supervisor **phát triển repo bằng Claude Code**;
không phải lệnh vận hành client/red/blue. Hướng dẫn riêng:
[AUTONOMOUS_EXECUTION](docs/AUTONOMOUS_EXECUTION.md).

Tài liệu chi tiết: [world](docs/CONTINUOUS_WORLD_VI.md),
[môi trường](docs/ENVIRONMENTS_VI.md), [Agent Office](agent-office/README.md),
[learning](docs/AGENT_LEARNING_VI.md), [rollback](docs/ROLLBACK_VI.md).
