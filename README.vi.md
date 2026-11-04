# SABER — Client / Red Team / Blue Team Lab

[English](README.md) | **Tiếng Việt**

**Mới: bộ SOC lab nhiều dịch vụ và VM** đã có mã triển khai cho ba preset
`linux-small`, `windows-ad`, `expanded`. Bắt đầu ở [SOC Lab — triển khai và nghiệm thu](docs/SOC_LAB_VI.md).
Nhóm lệnh là **`saber lab`**: business app, worker từng đội, Chromium, collector, OpenSearch,
Zeek, agent-office; bản AD có script Hyper-V/domain/Sysmon và phản ứng có rollback.
Đã kiểm thử local bằng HTTP, subprocess và Chromium thật. **Chưa chạy nghiệm thu toàn bộ Docker/AD
trên máy phát triển này**; `lab verify` phải đạt trên máy đích mới xác nhận runtime.
Office đã có bằng chứng từng job và ảnh Chromium kiểm hash; blue có hunt/DFIR và handoff,
Windows có queue tác vụ do agent điều phối. Range đã nối **learning có replay/pin/rollback,
vault phân tích Ghidra/IDA/Volatility/YARA/PCAP, SOAR có xác minh hiệu ứng và backup/restore**.
Xem [phạm vi hoàn thiện và bằng chứng kiểm thử](docs/SOC_COMPLETION.md).
Đợt rà soát xuyên suốt gần nhất: [các lỗi đã sửa, kiểm chứng và phần còn cần máy đích](docs/END_TO_END_AUDIT_VI.md).

| Nhu cầu trên máy lớn | Hướng dẫn |
|---|---|
| Dựng ba cỡ lab, chỉnh agents, mở Office | [Triển khai SOC](docs/SOC_LAB_VI.md) |
| Phân tích binary/memory/PCAP, kiểm tra công cụ | [Analysis](docs/SOC_ANALYSIS_VI.md) |
| Playbook và tích hợp Shuffle/webhook | [SOAR](docs/SOC_SOAR_VI.md) |
| Agent học từ lỗi và rollback skill | [Learning](docs/SOC_LEARNING_VI.md) |
| Sao lưu, chuyển máy, khôi phục | [Recovery](docs/SOC_RECOVERY_VI.md) |

Ghidra/IDA và symbols do operator đặt vào `tools/`; IDA cần bản có quyền headless.
Mặc định SOAR dùng backend tích hợp; adapter Shuffle dành cho instance riêng của lab.
Bundle có 13 service definitions, không tự cài mọi sản phẩm SOC thương mại.

`saber world` / `saber env` dưới đây vẫn là chế độ nhẹ. Chọn profile `vm` trong `env`
không đồng nghĩa đã dựng SOC lab hoặc domain; muốn các bộ mới hãy dùng `saber lab`.

SABER chạy một thế giới ứng dụng liên tục: client làm việc, red team thử điểm yếu
trong lab, blue team quan sát log và xử lý case. Có thể dùng baseline scripted hoặc
bật Gemini cho các agent lập kế hoạch. Project còn có bộ lõi benchmark SOC riêng.

**Phạm vi chế độ world/env:** HTTP và thay đổi trạng thái ứng dụng được thực thi thật;
tài khoản, dữ liệu và kỹ thuật trong world là mô phỏng. Các actor chia sẻ một runtime
Python, chưa phải desktop/VM riêng. Chế độ **`--execution native`** bổ sung process
con cho mỗi thao tác cùng bằng chứng PID/command line, file, DNS và TCP thật của
workload. Sensor chưa giám sát toàn OS; xem [phạm vi và lệnh chạy](docs/NATIVE_TELEMETRY_VI.md).
Kết quả mang nhãn `DEV_SIMULATION_ONLY`.

## Chọn môi trường

| Profile | Dành cho | Nơi thực thi | Điều kiện |
|---|---|---|---|
| `local` | Chạy thử nhanh, phát triển | Process Python trên máy hiện tại | Python 3.12+ |
| `sandbox` | Muốn container có thể tái tạo | Một Linux container chứa world | Docker Linux engine + Compose |
| `vm` | Người dùng tự dựng VM | Chạy bundle bên trong guest | VM có Python 3.12+ và uv |
| `remote` | Muốn dùng máy lab/server khác | Chuyển bundle và chạy trên server | Server có Python 3.12+ và uv |

VM có thể do Hyper-V, VMware hoặc KVM/Proxmox quản lý. SABER không tự tạo VM hay
kết nối SSH. Profile không tự thêm trình duyệt, Windows/AD, shell hoặc điều khiển snapshot.
Cấu hình SIEM/SOAR có sẵn hiện hỗ trợ **inventory và kiểm tra HTTP health**; chưa tự
kết nối luồng log hay hành động phòng thủ với sản phẩm bên ngoài.

- [Hướng dẫn đầy đủ từng môi trường](docs/ENVIRONMENTS_VI.md)
- [Notes — tra nhanh các lệnh chạy](notes.md)
- [Log native và xem riêng từng agent](docs/NATIVE_TELEMETRY_VI.md)
- [Cấu hình mẫu](config/environments/)
- [Commit và rollback](docs/ROLLBACK_VI.md)

## Chuẩn bị

Dùng terminal ở thư mục project với Python 3.12+ và uv. Tái sử dụng virtualenv đã có.
Không cần Docker để chạy local hoặc test offline.

```powershell
uv sync --locked
uv run saber --help
uv run saber env list
```

Với virtualenv có sẵn, có thể thay `uv run saber` bằng
`.\.venv\Scripts\python.exe -m saber.cli.main` trên Windows.

## Option 1 — sandbox

```powershell
uv run saber env init --profile sandbox --name sandbox-demo --clients 4 --out runs/env-sandbox.json
uv run saber env doctor --config runs/env-sandbox.json
uv run saber env render --config runs/env-sandbox.json --out runs/bundle-sandbox
uv run saber env up --bundle runs/bundle-sandbox
uv run saber env status --bundle runs/bundle-sandbox
uv run saber env report --bundle runs/bundle-sandbox --out runs/sandbox-report-1.json
uv run saber env down --bundle runs/bundle-sandbox
```

`init` tạo cấu hình, `render` xuất source/bundle, `up` mới yêu cầu build/start container.
Đường dẫn tạo mới phải chưa tồn tại. `doctor` không tự mở Docker Desktop.
Container mặc định không có mạng ngoài, không publish cổng, chạy non-root và có giới
hạn RAM/CPU/PID. Dữ liệu ở named volume; `down` giữ dữ liệu. Tiếp tục bằng:

```powershell
uv run saber env up --bundle runs/bundle-sandbox --resume
```

## Option 2 — VM do người dùng tự dựng

Tạo VM bằng hypervisor đang dùng, sau đó xuất bundle trên máy phát triển:

```powershell
uv run saber env init --profile vm --name vm-demo --clients 8 --out runs/env-vm.json
uv run saber env render --config runs/env-vm.json --out runs/bundle-vm
```

Chuyển `bundle-vm` vào guest. **Các lệnh tiếp theo chạy trong terminal VM**, tại
thư mục `bundle-vm/source`:

```powershell
uv sync --frozen --no-dev
uv run --no-sync saber env run --config ../environment.json --out ../world --ticks 30 --on-target
uv run --no-sync saber env run --config ../environment.json --out ../world --forever --on-target
```

`--on-target` xác nhận vị trí terminal; không tạo hoặc truy cập VM từ xa. Người dùng
quản lý tài nguyên guest, mạng và snapshot. [Runbook VM/server](docs/ENVIRONMENTS_VI.md).

## Option 3 — máy lab/server riêng

Dùng `--profile remote` khi init, render bundle rồi chuyển sang server. Chạy các lệnh
bên trong `source` giống VM, với `--on-target`. Dữ liệu và agents chạy trên server đó.
Không cần expose HTTP control plane ra Internet/LAN để xem báo cáo.

## Option 4 — local

```powershell
uv run saber env init --profile local --clients 4 --out runs/env-local.json
uv run saber env run --config runs/env-local.json --out runs/world-local --ticks 30
uv run saber env run --config runs/env-local.json --out runs/world-local --forever
```

Từ terminal thứ hai:

```powershell
uv run saber world status --out runs/world-local
uv run saber world stop --out runs/world-local
```

Thêm `--resume` khi muốn chạy lại sau STOP. Sửa roster trước lần chạy đầu; world đã có
sẽ từ chối cấu hình khác. Dùng thư mục mới để thử cấu hình khác.
Các lệnh `world init/run/supervise/status/stop` vẫn được giữ nguyên; `world supervise`
có thể restart process lỗi với số lần giới hạn.

## Đội blue có 12 chuyên môn

Tạo world mới có đủ chuyên môn (mặc định cũ vẫn là 6 vai blue):

```powershell
uv run saber world init --out runs/soc-specialists --clients 4 --blue-specialists
uv run saber world run --out runs/soc-specialists --ticks 30
# Chạy liên tục sau khi xem kết quả:
uv run saber world run --out runs/soc-specialists --forever
```

| Nhóm | Chuyên môn |
|---|---|
| Điều phối / phát hiện | Lead, monitoring, threat hunting |
| Điều tra | DFIR, malware/RE, network, threat intelligence, identity |
| Phòng thủ / vận hành | Incident response, detection engineering, SOC platform, recovery |

Có thể tạo nhiều actor cùng chuyên môn hoặc cấu hình `specialties` để một actor kiêm nhiệm.
Blue có query log phân trang, case/finding có dẫn chứng, task có nhận việc/bàn giao,
notebook riêng, snapshot chứng cứ có hash, kiểm thử/version/rollback rule và kiểm tra
client phục hồi. `wait`/`finish` thực sự ngừng hành động của actor. Agent-office hiển thị
chuyên môn, task và trạng thái này.

Baseline scripted thu thập/xử lý theo policy có sẵn; nhiệm vụ chuyên môn có mục tiêu tự do
cần planner hoặc operator đánh giá và kết luận. Công cụ chạy trên application lab;
Ghidra/IDA/EDR/SIEM ngoài lab vẫn cần adapter và dữ liệu thực. Xem
[cách dùng, quyền công cụ và giới hạn](docs/SOC_SPECIALISTS_VI.md).

## Bật Gemini

Agent có [luồng rút kinh nghiệm](docs/AGENT_LEARNING_VI.md): ghi kết quả riêng → tổng kết
theo task/case/chu kỳ → đề xuất bài học → replay so bản cũ/mới → phát hành phiên bản skill
cục bộ khi qua gate. Worker dùng chung budget/pool của đội. Mặc định scripted chỉ ghi
nhận; reflection cần model. Cần suite do operator cấp để tự đánh giá/phát hành; có
[mẫu phát triển cho client](config/learning/client-session.json). Agent-office hiển thị
counters học; case đang chạy giữ phiên bản skill ổn định. Đây chưa phải bằng chứng
Gemini tự cải thiện chất lượng SOC đầu cuối.

Mọi profile mặc định scripted, không gọi API. Model mặc định: `gemini-3.5-flash-lite`.
File key do chương trình nạp; không đưa vào Git/bundle.

| Nhóm | Vị trí key trong file |
|---|---|
| Client | 1–200 |
| Red | 201–400 |
| Blue | 401 đến cuối |

Key chuyển trong đúng pool khi chạm giới hạn hoặc gặp lỗi. Cursor, usage và cooldown
tồn tại qua restart. Khi API lỗi/hết budget, scripted fallback tiếp tục. Đây là **HYBRID**.
Local/VM/server: thêm `--llm --key-pool PATH --call-budget 200` vào `env run`. Sandbox:

```powershell
uv run saber env up --bundle runs/bundle-sandbox --llm --key-pool keys_pool.txt --call-budget 200 --resume
```

Sandbox Gemini dùng manifest riêng bật outbound cho controller và mount key chỉ đọc.
Egress chưa lọc theo domain. Budget `200` là **200 lượt HTTP tổng trong vòng đời world**,
gồm retry/restart, không phải mỗi key. Lệnh không đổi billing tier.
Xem `llm.successes`, `llm.by_team`, `llm_pools` và nguồn hành động `llm` để xác nhận.
[Hướng dẫn world/Gemini](docs/CONTINUOUS_WORLD_VI.md).

## Quan sát và dữ liệu

| File trong thư mục world | Nội dung |
|---|---|
| `config.json` | Cấu hình giữ ổn định cho world |
| `report.json` | Tick, kết quả, usage và trạng thái pool |
| `office.json` | Snapshot cho viewer: roster, nguồn hành động, counter, chỉ số quota |
| `learning.json` | Trạng thái học, version IDs và epoch; không có nội dung notebook/lesson |
| `access.jsonl` | Log thao tác ứng dụng, có rotation |
| `world.sqlite3` | Trạng thái, case, journal và ledger đánh giá |
| `STOP` | Yêu cầu dừng; tiếp tục bằng resume rõ ràng |

Thư mục world là đường dẫn `--out`; sandbox dùng `/data` trong named volume. Không
cấp database/ground truth cho agents. Xem world từ terminal thứ hai (Node.js 18+,
không cần cài npm dependencies):

```powershell
node agent-office/bin/agent-office.js watch --world runs/world --open
# Sandbox: thay bằng đường dẫn bundle đã env up
node agent-office/bin/agent-office.js watch --bundle runs/my-sandbox --open
```

Thay `runs/world` bằng thư mục `--out` thực tế. Viewer hiển thị Client/Red/Blue,
profile, scripted/Gemini, nguồn hành động và quota theo đội; chỉ đọc chỉ số key.
Bấm robot, màn hình/bàn hoặc thẻ agent để xem timeline thao tác, mục tiêu, HTTP status
và phản ứng blue gắn với bằng chứng của case. Lịch sử trên viewer là cửa sổ có giới hạn;
HTTP thành công không tự chứng minh tấn công thành công. Xem [notes](notes.md) để chạy demo.

Blue có thêm điều tra log nhập (EDR CSV, Apache/IIS, text): giữ bản gốc/hash, truy vấn theo
timeline/IP/process, ghi nhận định dẫn chứng, lưu tiến độ và rà thiếu sót phản ứng. Office hiện
query, mẫu log và gaps; `REVIEWED` không phải xác minh mitigation. Xem
[lệnh nhập log, chạy demo và dùng Gemini](docs/FORENSICS_VI.md).
Office chia ba khu Clients/Red/Blue, chọn 12 hoặc 24 bàn mỗi đội (36/72 slots).
Phân trang theo từng đội để xem đủ roster 200 agent; nút phía trên zoom từng khu.
Thêm slots không tạo thêm agent. Sandbox giữ mạng cô lập;
VM/server chạy viewer tại máy đích rồi forward cổng loopback. Xem
[hướng dẫn Agent Office](agent-office/README.md) và
[hướng dẫn world](docs/CONTINUOUS_WORLD_VI.md).
`env doctor --probe-services` chỉ gọi GET health của dịch vụ đã được cho phép trong
inventory. Một HTTP 200 không xác nhận SIEM/SOAR adapter hoạt động.

## RAM và mức sẵn sàng

Giới hạn mặc định 2 GiB trong sandbox dành cho **runtime ứng dụng hiện tại**, chưa gồm
trình duyệt, desktop Windows, SIEM, SOAR hoặc bộ phân tích mã độc. Những thành phần đó
cần tài nguyên và tích hợp riêng.

Đã kiểm tra runtime local và source export bằng subprocess thật, STOP/resume và HTTP
health bằng server test thật. Compose được kiểm tra cấu hình khi có CLI.
**Docker Linux engine trên máy phát triển hiện chưa chạy**, nên chưa xác minh build/
start container hoặc triển khai trong guest/server riêng. Không có `READY_BENCHMARK`.

## Kiểm thử và rollback

Skills có kiểm tra riêng: 18 skills, 15 sổ tay nghiệp vụ và 56 tài liệu tham chiếu.
Đã rà nguồn và bổ sung cả client/red/12 chuyên môn blue: [bảng nội dung, nguồn và kiểm chứng](docs/ALL_SKILLS_COVERAGE_VI.md).
World/range nạp hướng dẫn cốt lõi, contract và cho mỗi đội tra cứu chuyên đề bằng `consult_skill`;
population/benchmark nạp tài liệu theo case.
Bundle mang theo các reference cần thiết. Xem [hướng dẫn skills](docs/SKILLS_VI.md).
DFIR có 13 chuyên đề, 12 playbook và 12 nhóm hồ sơ; xem [bảng đối chiếu năng lực, nguồn và kiểm thử](docs/DFIR_CAPABILITY_COVERAGE_VI.md)
và [review handbook](docs/DFIR_HANDBOOK_REVIEW_VI.md). World cũ giữ skill đã pin; dùng world/bundle mới để nhận baseline mới.
Đã có [rà soát nội dung theo yêu cầu và catalog](docs/SKILLS_REVIEW_VI.md): sửa các quy tắc kết luận thiếu bằng
chứng và bổ sung công việc/bàn giao qua nhiều lượt. PASS cấu trúc chưa chứng minh chất lượng suy luận model
hoặc tích hợp công cụ SOC thật.

```powershell
uv run pytest --junitxml=runs/quality-tests.xml
uv run python scripts/check_skills.py --out runs/skills-check/audit.json
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts
uv run mypy --platform linux
uv run mypy --platform win32
uv run python scripts/validate_catalog.py
npm --prefix agent-office test
git log --oneline --decorate -15
```

Test offline không dùng key thật/gọi LLM. Live check là thao tác opt-in riêng trong
`scripts/smoke_world_gemini.py`. Thay đổi được chia commit theo chức năng; xem
[checkpoint và cách dùng git revert/worktree](docs/ROLLBACK_VI.md).
Git revert chỉ hoàn tác code: dừng runtime, backup data/volume trước khi đổi phiên bản.
`env down` không xóa volume. Snapshot VM được quản lý ở hypervisor.
CI kiểm tra Office trên Linux và Windows, đồng thời build lại để phát hiện
`viewer/index.html` chưa cập nhật theo source. Khi sửa viewer, chạy
`npm --prefix agent-office run build:viewer` với dependencies đã cài từ lockfile.

## Workflow khác

- [Benchmark readiness](docs/READINESS.md): trạng thái dữ liệu, scorer và tích hợp.
- `saber task`, `smoke`, `experiment`: benchmark offline, độc lập với deployment profile.
- [Development supervisor](docs/DEVELOPMENT_SUPERVISOR.md): `run.sh` điều phối công việc
  phát triển bằng Claude Code; không phải lệnh bật thế giới client/red/blue.
- [Environment first](docs/ENVIRONMENT_FIRST.md): tái sử dụng hạ tầng hiện có.
- [Security](docs/SECURITY.md): phạm vi lab và quyền thực thi.
- [ADR environment profiles](docs/adr/0003-environment-profiles.md): quyết định thiết kế.

## Giấy phép

SABER giữ trạng thái **Proprietary** như metadata hiện có. Xem [LICENSE](LICENSE)
để biết thông báo quyền và đầu mối liên hệ. Toàn bộ repository chưa được phát hành
dưới một giấy phép mã nguồn mở.

Thành phần [agent-office](agent-office/LICENSE) giữ giấy phép MIT riêng như đã khai báo
trong package. Dependency, dataset, detection rule và công cụ bên thứ ba giữ điều khoản
của chúng; xem thêm [nguồn gốc dữ liệu](docs/EVAL_DATA_PROVENANCE.md).
