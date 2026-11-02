# SOC Lab — build ở máy nhỏ, triển khai ở máy lớn

`saber lab` là bộ triển khai riêng với dịch vụ thực thi, telemetry và SIEM. `saber world`
và `saber env` vẫn dùng được cho demo nhẹ. Bundle mới không nâng cấp dữ liệu world cũ.

## Ba lựa chọn

| Preset | Ngân sách máy đích dự kiến | Agents client / red / blue | Executor mỗi đội | Windows guests |
|---|---|---|---|---|
| `linux-small` | 32 GB RAM, 6 CPU, 250 GB trống | 2 / 3 / 6 | 1 | Không |
| `windows-ad` | 64 GB RAM, 8 CPU, 500 GB trống | 4 / 3 / 6 | 1 | 1 DC, 2 workstation, 1 file server |
| `expanded` | 128 GB RAM, 16 CPU, 1 TB trống | 12 / 3 / 6 | 3 | 1 DC, 6 workstation, 1 file server |

Đây là mức phân bổ ban đầu, không phải số đo tải thực tế. RAM dành cho VM cố định;
containers có giới hạn riêng. `expanded` tăng quy mô executor/guest, chưa phải cụm SIEM HA.
Sửa `actors`, `workers_per_team`, `tick_seconds`, dung lượng và VM trong JSON **trước khi render**.
Logical agent không đồng nghĩa một máy: agents cùng đội dùng các worker của đội đó.
Các đội được lập lịch đồng thời; số job đồng thời trong mỗi đội tối đa bằng số worker.
Windows job do agent chọn được đưa vào queue riêng rồi relay gọi scheduled task SYSTEM
có hành vi cố định trong guest; không có model riêng chạy trong từng desktop.

## Dịch vụ và đường đi dữ liệu

```text
                     Controller + skills + optional Gemini
                           |         |         |
                         client     red       blue   (team workers)
                           |         |         |
                           +---- Business app --+
                                  |       |
                              file/HTTP   Zeek (app network namespace)
                                  |       |
                              Collector / raw SQLite / cases
                                  |                 |
                              OpenSearch       response gateway
                                  |                 |
                              Dashboards       app ACL / session

Windows DC / workstations / SMB --> Sysmon + Security
                  |                       |
        PowerShell Direct relay ----------+--> Collector
                  ^                               |
                  +-- scoped AD response queue ---+

Controller public snapshot --> agent-office
```

Mỗi job chạy một process Python thật; client có Chromium thật, app đọc/ghi tài liệu trên
filesystem, red kiểm tra quyền đọc và copy dữ liệu tổng hợp vào workspace. Blue truy vấn
log, xác minh hash, quản lý case và áp dụng chặn session/ACL thật trong app.
AD có tài khoản thử nghiệm `saber-red`, file share và bài tạo logon thất bại có giới hạn.
Blue có thể yêu cầu khóa đúng tài khoản thử nghiệm, relay kiểm tra AD và hẹn mở lại sau 5 phút.
`QUEUED`/HTTP 202 không phải đã khóa thành công. `MITIGATED` ghi nhận phản ứng tại thời điểm đó,
không khẳng định tài khoản vẫn bị khóa sau TTL.

## Chuẩn bị bundle, chưa chạy lab

Ở checkout trên máy phát triển:

```powershell
uv sync --locked
uv run saber lab list
uv run saber lab init --preset linux-small --name soc-small --out runs/soc-small.json
uv run saber lab render --config runs/soc-small.json --out runs/soc-small-bundle
uv run saber lab validate --bundle runs/soc-small-bundle
```

Thay preset bằng `windows-ad` hoặc `expanded`; mỗi bundle chọn `name` và thư mục mới.
Cấu hình mẫu ở [config/labs](../config/labs/). `render` copy source/skills/viewer/script
theo allowlist, tạo manifest hash; không copy key pool, `.env`, VHDX hay dữ liệu runtime.
Không cần Docker chạy để render. Chuyển nguyên bundle sang máy đích, giữ các source file
nguyên trạng. Nếu sửa code/config, render bundle mới; không sửa manifest để bỏ kiểm tra.

## Khởi động phần Linux/container trên máy đích

Cần Docker Linux Engine + Compose v2, Python 3.12+, uv. Có thể chạy trong Linux VM/server
hoặc Docker Desktop Linux trên host Windows đủ tài nguyên. Lần build đầu cần tải images
và dependencies; sau đó có thể dùng cache của môi trường đích. Kernel chạy OpenSearch cần
`vm.max_map_count >= 262144`; `doctor` chỉ đọc, không thay thiết lập hệ thống.

Ở thư mục `BUNDLE/source` trên máy đích:

```powershell
uv sync --frozen --no-dev
uv run --no-sync saber lab doctor --config ../lab.json --storage ..
uv run --no-sync saber lab credentials --bundle ..
uv run --no-sync saber lab up --bundle .. --on-target
uv run --no-sync saber lab status --bundle ..
uv run --no-sync saber lab analysis self-test --bundle ..
uv run --no-sync saber lab verify --bundle ..
```

`credentials` chạy đúng một lần, không in giá trị và không tự rotate. Giữ `.secrets/` riêng
tư; trên Windows đặt ACL thư mục chỉ cho tài khoản vận hành. Backup credential cùng dữ liệu;
tạo token mới rồi dùng lại volume cũ sẽ làm mất đồng bộ. Không commit credential vào Git.

Controller bắt đầu làm việc sau khi app/worker đã healthy. Chờ khoảng 1–3 phút để có chuỗi
client → red → case → blue → bằng chứng chặn và để indexer nhận log, rồi chạy `verify`.

- Agent Office: `http://127.0.0.1:7788` — bấm agent xem 12 job gần nhất, kết quả,
  process launch/exit, bằng chứng ứng dụng và hash artifact; client có ảnh Chromium thật.
- OpenSearch Dashboards: `http://127.0.0.1:5601` — tạo index pattern `saber-<name>`, time field `ts`.
- Collector: `127.0.0.1:7789`; endpoint đọc/ghi có capability token, chỉ health công khai.
- Analysis vault: `127.0.0.1:7792`; SOAR gateway: `127.0.0.1:7793`, đều cần capability.
- Máy khác xem qua SSH tunnel tới localhost của máy đích. Không đổi các port thành public.

Office hiển thị ảnh trình duyệt chụp tại job được ghi tick/ID, không truyền RDP/VNC desktop guest.
Controller kiểm hash ảnh và bằng chứng gốc trước khi tạo export đã ẩn thông tin nhạy cảm.
Cửa sổ tối đa 12 job/agent và 2 MB/export; ảnh gần nhất tối đa 1 MB. Dữ liệu đầy đủ vẫn
ở collector/worker. Checkbox lịch sử riêng chuyển giữa toàn cửa sổ và job đang chọn.
Log Sysmon/Zeek ngoài các bằng chứng gắn với job xem bằng Dashboards hoặc `lab logs`.
Viewer đọc export tĩnh, không nhận credential hay quyền chạy lệnh lên worker.

Các công cụ blue đã có: truy vấn theo host/kind/thời gian và các trường principal,
command line, PID, IP, domain, hash, path, event code, job ID; hunt mạng/identity,
case timeline/export có kiểm hash, kiểm health sensor và đối chiếu phản ứng/recovery.
Lead có thể giao case; mỗi đội có hộp trao đổi riêng. `publish_rule` lưu rule replay trong
lab sau khi tái hiện bằng chứng, chưa triển khai rule liên tục vào một SIEM bên ngoài.
DFIR/malware/network có vault mẫu theo hash và adapter binary/memory/PCAP:
[analysis và cài công cụ](SOC_ANALYSIS_VI.md). Blue IR/content mặc định dùng
[SOAR playbook](SOC_SOAR_VI.md), có backend tích hợp hoặc Shuffle/webhook riêng.
[Learning](SOC_LEARNING_VI.md) ghi episode riêng, replay bằng suite của operator,
publish phiên bản bất biến và giữ pin trong case/job đang chạy.
[Backup/restore](SOC_RECOVERY_VI.md) lưu volume, credential dịch vụ và export guest cùng mốc.
Theo dõi phạm vi code và nghiệm thu ở [SOC_COMPLETION](SOC_COMPLETION.md).

## Bật Gemini, giữ các pool 200 / 200 / còn lại

Chỉ controller nhận key pool. Workers, app, collector và viewer không nhận API key.
Trên máy đích, dùng model ID đang có quyền sử dụng trong tài khoản của bạn:

```powershell
uv run --no-sync saber lab up --bundle .. --on-target --llm --key-pool /private/keys_pool.txt --model MODEL_ID --call-budget 300
```

Pool được chia theo vị trí như runtime cũ: 200 client, 200 red, phần còn lại blue.
Quota/cursor/budget nằm trong database controller và giữ qua restart. Mỗi lần thử API
đều tính budget. Hết quota/budget hoặc response sai định dạng thì hành động được gắn
`scripted-fallback`, không giả là Gemini đã chọn.
Overlay Gemini cho **controller** thêm mạng outbound; đây không phải firewall allowlist
theo domain. Các executor vẫn chỉ có mạng lab nội bộ. Lệnh không đọc/in key qua terminal.

## Thêm Windows/AD

Chạy phần này trên **host Hyper-V Windows Pro/Enterprise hoặc Windows Server**.
Chuẩn bị server VHDX và workstation VHDX UEFI/Generation 2 do bạn cung cấp, có giấy phép phù hợp,
đã generalize và có unattended first boot hoàn tất với tài khoản Administrator đã biết.
Windows workstation cần edition hỗ trợ join domain. Base image phải giữ nguyên sau khi tạo
differencing disks. Script không tải Windows, không tự bypass OOBE/TPM/license.

PowerShell mở quyền Administrator **trên host lab**, không phải laptop đang phát triển:

```powershell
$base = Get-Credential -UserName Administrator -Message 'Administrator của base images'
$dsrm = Read-Host 'DSRM password cho domain mới' -AsSecureString
.\windows\Provision-Lab.ps1 -Bundle . -VmRoot D:\SaberVMs -ServerVhdx D:\Images\server.vhdx -WorkstationVhdx D:\Images\workstation.vhdx -BaseCredential $base -DsrmPassword $dsrm -OnTarget
$domain = Get-Credential -UserName 'saber.test\Administrator' -Message 'Lab domain administrator'
.\windows\Install-Sensors.ps1 -Bundle . -SysmonExe D:\Tools\Sysmon64.exe -DomainCredential $domain -OnTarget
.\windows\Relay-Lab.ps1 -Bundle . -DomainCredential $domain -OnTarget
```

Dùng bundle `windows-ad`/`expanded` ở thư mục hiện tại. Provisioner tạo switch **Private**,
không default gateway, subnet `172.28.80.0/24`, join domain và tạo synthetic users/group/share.
VM name có prefix của bundle; script chỉ chạm VM có ownership marker đúng. Phiên bản
provisioner này dùng subnet trên; cấu hình subnet tùy biến cần cập nhật provisioning trước.
`Install-Sensors` yêu cầu Sysmon có chữ ký Microsoft hợp lệ và tạo checkpoint `SABER-baseline`.
Guest process/file/network/DNS tới từ Sysmon; Security tới từ Windows Event Log.
Relay giữ bookmark sau ACK, dùng ID xác định để tránh trùng khi gửi lại, không in credentials.

Agent có thể chọn `windows_work`, `windows_recon`, `windows_failed_logon`,
`windows_inventory` hoặc `windows_collect_evidence` theo quyền của vai trò.
Client/red chỉ được chọn workstation thuộc bundle; thao tác AD chỉ nhắm tài khoản lab.
Receipt `SUCCEEDED` phải có PID và các bằng chứng phù hợp với thao tác. Queue không cho
agent tự chạy lại một job chưa rõ kết quả. Với `INDETERMINATE`, agent chỉ kiểm tra trạng thái.
Sau khi người vận hành đã kiểm tra guest, dừng task cũ và xác nhận có thể tiếp tục:

```powershell
uv run --no-sync saber lab reconcile-guest --bundle .. --job-id JOB_UUID --reason "Inspected guest and stopped the original task; safe to resume."
```

Lệnh lưu lý do đối soát và mở lại agent; kết quả gốc vẫn là `INDETERMINATE`, không được
đổi thành thành công. Relay credential chỉ người vận hành giữ, agent không có quyền đối soát.
Script guest mới cần được copy bằng `Install-Sensors.ps1` từ bundle mới trên host lab.

Nếu SOC chạy ở Linux server khác: copy cùng bundle + `.secrets/relay.json` riêng tư sang Hyper-V host,
mở SSH tunnel từ host tới collector của Linux server (`127.0.0.1:7789` ở cả hai đầu),
rồi chạy relay. Không mở WinRM ra LAN; PowerShell Direct đi qua Hyper-V.
Sau provisioning, quay lại terminal `BUNDLE/source` của SOC và chạy `lab verify`.
Bản AD/expanded cần log gần đây của **từng guest**, domain đúng, Sysmon và Security mới pass.

## Linux OS telemetry và phạm vi sensor

Mặc định: process launch/exit đo trực tiếp bởi executor; `/proc` polling bổ sung tiến trình,
TCP trong namespace và hash file workspace. Polling có thể bỏ lỡ process/kết nối rất ngắn.
Zeek bắt metadata mạng **namespace của app**, không tự giám sát mọi guest hoặc mọi mạng host.
Không capture payload/credentials thành pcap. Zeek cần NET_RAW/NET_ADMIN trong namespace app,
không dùng host network hay privileged container.

Để có kernel audit trên **Linux VM lab riêng**, cài auditd trong VM, chạy
`linux/Install-Audit.sh --on-target` bằng root trong guest. Sau đó chạy package đã xuất:

```bash
python -m saber.lab.logship --source audit --logs /var/log/audit --data /var/lib/saber/audit-outbox --credentials /private/linux-audit.json --collector http://127.0.0.1:7789 --host linux-audit
```

Cấp file `.secrets/linux-audit.json` riêng và SSH tunnel loopback tới collector nếu khác máy.
Audit rules ghi exec của user đăng nhập UID >= 1000 và I/O tại `/var/lib/saber/workspace`.
Chúng không hứa hẹn mọi hành động root/container. Bắt toàn bộ mạng của nhiều VM cần sensor
và port mirroring ở hypervisor; cấu hình đó phụ thuộc môi trường đích.

## Vận hành, lưu trữ và phục hồi

Các lệnh dưới chạy ở `BUNDLE/source`:

```powershell
uv run --no-sync saber lab logs --bundle .. --limit 100
uv run --no-sync saber lab logs --bundle .. --kind process.exit --limit 500
uv run --no-sync saber lab stop --bundle ..
uv run --no-sync saber lab resume --bundle ..
uv run --no-sync saber lab down --bundle ..
```

`logs` trả `next_cursor`; truyền JSON cursor đó vào `--cursor` để đọc trang kế tiếp.
100/1000 là giới hạn mỗi trang, không phải tổng số log được lưu. `stop` chỉ dừng controller,
sensor vẫn chạy. `down` dừng containers và giữ named volumes. Chạy lại `up` dùng checkpoint cũ.
VM và relay là process riêng: dừng relay bằng Ctrl+C, dừng guest bằng
`windows/Stop-Lab.ps1 -Bundle . -OnTarget`. Thêm `-RestoreBaseline` để khôi phục toàn bộ
VM thuộc lab, giữ chúng tắt; không rollback một DC đơn lẻ giữa domain đang chạy.

Raw events/outbox/jobs/cases lưu SQLite WAL; collector đẩy tài liệu thật sang OpenSearch và
chỉ đánh dấu delivered sau ACK. Sau `retention_days` (mặc định 7), raw đã ACK được nén thành
`/data/archives/*.jsonl.gz`, fsync và kiểm tra trước khi bỏ khỏi hot SQLite. Bản chưa ACK không bị
xóa. Bằng chứng mới chuyển archive có index theo ID; DFIR và endpoint `/evidence/{id}`
đọc lại archive sau khi kiểm cả hash file và hash event. Archive hỏng trả lỗi, không coi là
bằng chứng hợp lệ. Các archive tạo bởi bản cũ chưa có index này cần tra file archive trực tiếp.
OpenSearch vẫn giữ lịch sử đã index; file archive có event + SHA-256. Hết disk budget
thì runtime dừng/không nhận thêm bằng chứng, không xóa ngầm. Controller và từng dịch vụ có
budget riêng; Zeek/indexer cần volume monitoring/backup ở host. Chạy liên tục vô hạn luôn cần
chính sách dung lượng/luân chuyển sang storage khác, không có bảo đảm vô hạn trên ổ đĩa hữu hạn.

Backup khi đã dừng controller, relay, workers và indexer: snapshot/copy **tất cả named volumes**,
bundle, `.secrets`, VHDX differencing chains và checkpoints. Restore vào lab riêng cùng phiên bản.
Git revert chỉ đổi code; không revert AD, database, policy hoặc quota nhà cung cấp.
Nếu job mất kết nối, actor giữ pending và hỏi receipt cũ. Không tự chạy lại effect chưa rõ.
Job không có receipt hoàn tất cần operator điều tra dữ liệu trước khi chọn reset bằng bundle mới.

## Đã kiểm thử gì, còn phải nghiệm thu gì

| Hạng mục | Kiểm tra tại máy phát triển | Nghiệm thu máy đích |
|---|---|---|
| Ba spec/bundle, manifest, secrets tách vai trò, Compose | Unit tests + render/Compose config | Build/pull images và khởi động |
| App, worker, controller, red/blue response | HTTP + subprocess thật, kiểm tra ACL/rollback, lost-response recovery | Cách ly và tải trên Docker |
| Browser | Chromium thật mở portal, ghi screenshot/hash | Browser trong worker image |
| Indexer | Kiểm thử hợp đồng HTTP/mapping/ACK; không mock thành runtime pass | OpenSearch thật, truy vấn khớp raw IDs |
| AD/Hyper-V/Sysmon | Parse PowerShell/XML + kiểm tra giao thức queue/receipt | Provision, domain join, event capture, rollback thật |
| Zeek/audit | Parser/checkpoint/partial line/redaction tests | Capture trên namespace/guest thật |
| Viewer | Protocol tests + Chrome mở bằng chứng cả ba đội, kiểm ảnh chụp thật từ worker | Snapshot từ controller container |
| Learning | Capture/reflection/replay/publish/pin/rollback với provider fixture | Đánh giá chất lượng lesson bằng Gemini thật |
| Analysis | YARA positive/negative thật, Volatility từ chối ảnh không hợp lệ | `analysis self-test`; mẫu phù hợp cho các adapter tùy chọn |
| SOAR | HTTP thật, mất phản hồi, callback, xác minh hiệu ứng; external protocol fixtures | Playbook trong container; instance Shuffle riêng nếu chọn |
| Recovery | Restore SQLite/outbox/artifact, hash, chống ghi đè/path traversal; parse Hyper-V | Khôi phục Docker volumes/OpenSearch và toàn bộ guest thật |

`verification.receipt.json` chỉ ghi `runtime_verified=true` khi các check live đạt. File được
render, unit test pass hoặc HTTP health đơn lẻ không đủ. Chưa tự nhận toàn bộ ba lab đã boot
trên phần cứng hiện tại. Workflow `soc-lab-target` chỉ chạy khi được gọi thủ công trên runner
có nhãn `saber-lab`; không khởi động hạ tầng trong CI thông thường.

Bộ này cung cấp SIEM bằng OpenSearch, SOAR/case gateway của SABER và analysis service.
Không tự cài mọi sản phẩm SOC, Wazuh/TheHive/Shuffle hay giấy phép IDA. Ghidra/IDA/symbols
được mount vào adapter đã có; Shuffle riêng dùng cấu hình kết nối và workflow của operator.
Phạm vi red hiện có là app ACL/collection và AD emulation có giới hạn; không phải thư viện
exploit cho mọi kỹ thuật. Skills mô tả nghiệp vụ rộng hơn danh sách tool đang thực thi.
Learning chỉ promote sau replay đạt gate, không tự sửa source skill từ kết quả thất bại.
Benchmark 175 subtasks, sealed truth và các gate đánh giá giữ nguyên; lab boot thành công
không làm các benchmark task chưa nghiệm thu trở thành READY.

Tham chiếu triển khai: [OpenSearch Docker](https://docs.opensearch.org/latest/install-and-configure/install-opensearch/docker/),
[Playwright Docker](https://playwright.dev/python/docs/docker),
[PowerShell Direct](https://learn.microsoft.com/en-us/windows-server/virtualization/hyper-v/powershell-direct),
[Sysmon](https://learn.microsoft.com/en-us/sysinternals/downloads/sysmon),
[Zeek logs](https://docs.zeek.org/en/current/reference/logs/index.html).
