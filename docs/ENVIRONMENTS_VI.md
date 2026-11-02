# Lựa chọn môi trường chạy SABER

## Phạm vi đã triển khai

Bốn profile triển khai **cùng runtime ứng dụng**: các actor client/red/blue, dịch vụ
HTTP nội bộ, trạng thái SQLite, log và case SOC. Mỗi world có một process Python;
actor là vai trò phần mềm, chưa phải một máy tính/desktop độc lập.

| Profile | Nơi chạy | Người quản lý môi trường | Phạm vi cô lập |
|---|---|---|---|
| `local` | Máy đang mở terminal | Người vận hành | Quyền ứng dụng; không có sandbox OS |
| `sandbox` | Một Linux container | Compose từ bundle | Cô lập container quanh toàn bộ world |
| `vm` | Bên trong VM tự dựng | Người dùng / hypervisor | VM bao quanh runtime; guest OS do người dùng quản lý |
| `remote` | Máy lab/server đã có | Người dùng / quản trị server | Theo cách server được triển khai |

Profile không cài SIEM/SOAR, tạo Windows desktop, điều khiển trình duyệt, chia actor
ra nhiều VM hoặc mở quyền thực thi shell. Các adapter hypervisor/OS trong benchmark
cũ vẫn giữ trạng thái blocked nếu chưa có tích hợp được xác minh.

## Tạo và kiểm tra cấu hình

Chạy tại checkout sau `uv sync --locked`:

```powershell
uv run saber env list
uv run saber env init --profile sandbox --name sandbox-demo --clients 4 --out runs/env-sandbox.json
uv run saber env validate --config runs/env-sandbox.json
uv run saber env doctor --config runs/env-sandbox.json
```

`init` chỉ tạo file mới, từ chối ghi đè. `validate` không gọi mạng. `doctor` chỉ đọc
thông tin máy hiện tại và kiểm tra Docker nếu profile cần nó; không mở Docker Desktop,
cài WSL hay tạo VM. Exit code 1 khi thiếu điều kiện nền. Kết quả RAM là thời điểm đo.
`runtime_verified=false` và `isolation_verified=false` không được đổi thành true chỉ
vì cấu hình hợp lệ hoặc daemon có phản hồi.

`world` chứa roster, tần suất hoạt động và cấu hình lưu trữ đã dùng bởi `saber world`.
`resources.memory_mb/cpus/pids` giới hạn container sandbox. Chúng **không** tự đổi
tài nguyên VM/server hoặc áp trần cho process `local`.

## Option 1: sandbox container

Yêu cầu Docker Linux engine đang chạy và Docker Compose. Trên Windows có thể dùng
Docker Desktop/WSL2. Không cần dựng VMware riêng cho từng client.

```powershell
uv run saber env render --config runs/env-sandbox.json --out runs/bundle-sandbox
uv run saber env up --bundle runs/bundle-sandbox
uv run saber env status --bundle runs/bundle-sandbox
uv run saber env report --bundle runs/bundle-sandbox --out runs/sandbox-report-1.json
uv run saber env down --bundle runs/bundle-sandbox
uv run saber env up --bundle runs/bundle-sandbox --resume
```

- `render` tạo bundle mới; không cài hoặc khởi chạy gì. Thư mục đích phải chưa tồn tại.
- `up` build image và yêu cầu Compose khởi chạy. Kiểm tra `status` và `report` để biết
  worker có hoạt động; thông báo đã gửi yêu cầu start chưa chứng minh API thành công.
- Mặc định là scripted, `network_mode: none`; HTTP loopback trong container vẫn chạy.
- Không publish cổng host, không mount Docker socket hoặc cả workspace. Container dùng
  UID/GID 10001, rootfs chỉ đọc, bỏ capabilities, giới hạn PID/RAM/CPU và log Docker.
- Dữ liệu nằm trong named volume. `down` giữ volume; SIGTERM yêu cầu STOP và chờ dừng
  có kiểm soát. `--resume` là yêu cầu dùng một lần; crash restart không tái dùng nó để
  xóa STOP mới của người vận hành.
- Build image cần tải base image/dependency. Điều này khác với quyền mạng lúc chạy.

Bật Gemini trong sandbox:

```powershell
uv run saber env up --bundle runs/bundle-sandbox --llm --key-pool keys_pool.txt --call-budget 200 --resume
```

Lệnh chọn **manifest hoàn chỉnh riêng** `compose.gemini.yaml`, bật mạng outbound cho
controller và mount file key chỉ đọc ở `/run/secrets/gemini-pool`. Không gộp hai file
Compose bằng `-f ... -f ...`. Key không được chép vào image/bundle. Egress ở profile
này **chưa lọc theo domain**; không dùng nó để chạy malware hay shell tùy ý.

Budget là tổng lượt HTTP của world, tồn tại qua restart. Chia key 200 client / 200 red /
phần còn lại blue vẫn do runtime hiện tại quản lý. `report.llm.successes` và hành động
có nguồn `llm` mới là bằng chứng suy luận/thực thi; xem hướng dẫn continuous world.

## Option 2: VM do người dùng tự dựng

1. Chọn Hyper-V, VMware, KVM/Proxmox hoặc hypervisor đang có. Tạo guest Windows/Linux
   và mạng lab của riêng nó. SABER không thực hiện bước này hay gọi API hypervisor.
2. Trong guest, chuẩn bị Python 3.12+ và uv. Tài nguyên VM do người vận hành đặt; profile
   này chạy app lab, chưa bao gồm desktop browser, SIEM hay bộ công cụ reverse engineering.
3. Tạo bundle trên máy phát triển rồi chuyển **toàn bộ bundle** vào VM:

```powershell
uv run saber env init --profile vm --name vm-demo --clients 8 --out runs/env-vm.json
uv run saber env render --config runs/env-vm.json --out runs/bundle-vm
```

4. Mở terminal **bên trong VM**, vào thư mục `bundle-vm/source`:

```powershell
uv sync --frozen --no-dev
uv run --no-sync saber env doctor --config ../environment.json
uv run --no-sync saber env run --config ../environment.json --out ../world --ticks 30 --on-target
uv run --no-sync saber env run --config ../environment.json --out ../world --forever --on-target
```

`--on-target` xác nhận terminal đang ở guest mong muốn; không phải phát hiện hypervisor
hay chứng minh cô lập mạng. Đưa key vào guest riêng nếu cần Gemini, sau đó thêm
`--llm --key-pool PATH_TRONG_GUEST --call-budget 200`. Không dùng đường dẫn của máy host.

Từ terminal guest thứ hai, cùng venv:

```powershell
uv run --no-sync saber world status --out ../world
uv run --no-sync saber world stop --out ../world
```

Lần chạy tiếp theo thêm `--resume`. Snapshot/restore guest là thao tác của hypervisor;
dừng world trước khi tạo bản sao trạng thái. Một VM runner không đồng nghĩa nhiều
máy client/red/blue: topology nhiều endpoint thật là tích hợp khác, chưa được profile này tạo.

## Option 3: server lab riêng / máy khác

Dùng `--profile remote`, tạo bundle giống VM, chuyển sang server đã có rồi chạy các
lệnh trong `source` trên server với `--on-target`. Server có thể là máy vật lý hoặc VM.
Không cần mở HTTP control plane của SABER ra LAN; dùng terminal/SSH của người vận hành
để xem report và log. SABER không lưu mật khẩu SSH và không tự chạy lệnh trên host khác.

Profile này giúp chuyển tải CPU/RAM/ổ đĩa sang máy khác. `doctor` chạy trên laptop chỉ
phản ánh laptop; muốn kiểm tra server phải chạy `doctor` trong terminal server.

## Option 4: local để phát triển và chạy thử

```powershell
uv run saber env init --profile local --clients 4 --out runs/env-local.json
uv run saber env run --config runs/env-local.json --out runs/world-local --ticks 30
uv run saber env run --config runs/env-local.json --out runs/world-local --forever
```

Không cần Docker hoặc VM. Dừng/xem trạng thái bằng `world stop/status --out runs/world-local`.
Sửa roster trước lần chạy đầu; sau khi world đã tồn tại, cấu hình khác bị từ chối để
tránh đổi danh tính hoặc quyền giữa chừng. Dùng thư mục world mới cho cấu hình khác.

## Dịch vụ SIEM/SOAR có sẵn

Mọi profile đều có danh sách `services`. Ví dụ đầy đủ ở
[`config/environments/services.example.json`](../config/environments/services.example.json).
Chỉ lưu tên biến môi trường chứa token, không nhập token/password vào JSON hoặc URL.

```json
{
  "name": "existing-siem",
  "capability": "siem",
  "api_base_url": "https://siem.lab.example",
  "health_check_path": "/REPLACE_WITH_HEALTH_PATH",
  "credential_env_name": "SABER_SIEM_TOKEN",
  "approved_for_read_only_use": false
}
```

Đặt URL/path đúng của dịch vụ lab, đánh dấu `approved_for_read_only_use=true` khi được
phép kiểm tra, rồi chạy:

```powershell
uv run saber env doctor --config runs/env-local.json --probe-services
```

Chỉ gửi GET đến health URL khai báo; không follow redirect, không quét mạng, không
in token/body lỗi. Token được gửi dạng Bearer; HTTPS bắt buộc khi gửi token tới host
không phải loopback. Auth flow khác cần adapter riêng.

**HTTP reachable chỉ là kiểm tra kết nối.** Hiện chưa tự ingest log vào Wazuh/Splunk,
đồng bộ case TheHive/IRIS hay thực thi SOAR. `adapter_verified` luôn false ở bước này.
File inventory cũ `config/existing-environment.json` của development supervisor là
schema riêng; không ghi đè hoặc tự chuyển quyền từ file đó.

## Dữ liệu, build và rollback

- Bundle chỉ xuất Python source, public catalog cần thiết, playbook đã chọn,
  `pyproject.toml`, `uv.lock` và các file viewer công khai được allowlist. Viewer nằm
  ở `agent-office/` ngoài Docker build context; không mang theo `node_modules`.
  Không xuất `.env`, key pool, `.git`, venv, runs hay dữ liệu riêng.
- File hash trong manifest xác định nội dung working tree được xuất; `source_revision`
  chỉ là commit nền. Hash không phải chữ ký chứng thực nguồn.
- Các manifest Compose được đối chiếu với profile hỗ trợ trước lifecycle. Không chỉnh
  trực tiếp bundle; sửa cấu hình nguồn và render thư mục mới. Bundle mới có project/
  volume riêng, không tự chuyển dữ liệu cũ.
- Export report trước `down`; report JSON không phải bản backup toàn world. Với container,
  backup named volume lúc đã dừng. Với guest/local, backup cả thư mục world lúc đã dừng.
- Đổi Git commit không khôi phục SQLite, volume, VM snapshot hoặc quota đã dùng.

Xem [quy trình commit và rollback](ROLLBACK_VI.md). Không có lệnh mặc định nào xóa volume.

## Quan sát bằng Agent Office

Node.js 18+ chỉ cần ở máy chạy viewer. Từ root repo:

```powershell
node agent-office/bin/agent-office.js watch --world runs/world --open
node agent-office/bin/agent-office.js watch --bundle runs/my-sandbox --open
```

Lệnh đầu dùng đúng thư mục `--out` local/guest. Lệnh sau đọc snapshot qua Docker host,
không thêm network/port cho sandbox. Từ bundle mới, cũng có thể chạy
`node agent-office/bin/agent-office.js watch --bundle .`. Bản runtime cũ chưa sinh
`office.json` cần cập nhật/rebuild theo quy trình bảo toàn dữ liệu; render bundle mới
tạo project/volume mới, không tự dùng lại world cũ.

VM/server chạy viewer tại máy đích rồi SSH forward cổng loopback về máy xem. Viewer
hiển thị profile được khai báo, đội agent, nguồn hành động, counters API và chỉ số key;
không tự xác nhận hypervisor hoặc kết nối SIEM/SOAR. Xem
[hướng dẫn Agent Office](../agent-office/README.md).

## Xác minh và giới hạn

Test tự động kiểm tra profile, export nguồn độc lập, gọi HTTP lab thật, STOP/resume,
đường gọi Compose, bảo vệ build context và health probe. Compose được kiểm tra cấu
trúc bằng CLI thật khi có CLI. Điều này không thay thế kiểm tra container/VM đang chạy.

Ở máy phát triển hiện tại Docker Linux engine chưa chạy, nên chưa xác minh build/start
container, giới hạn tài nguyên thực tế hoặc khởi động trong VM/server riêng. `doctor`
báo trạng thái thực tại máy gọi lệnh. Không có kết quả nào được nâng lên READY_BENCHMARK.

Tài liệu nền: [Compose services](https://docs.docker.com/reference/compose-file/services/),
[uv trong Docker](https://docs.astral.sh/uv/guides/integration/docker/).
