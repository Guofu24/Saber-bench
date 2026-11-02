# Log process, file, DNS và network của workload

`--execution native` chạy mỗi thao tác client/red/blue trong một **process Python thật**.
Controller lập lịch và giữ trạng thái world; process con gửi thao tác đến dịch vụ HTTP
lab, đo I/O rồi thoát. Mỗi lượt có PID mới, không phải một desktop hay process thường
trú riêng cho từng agent. `application` vẫn là chế độ mặc định.

## Nguồn và giới hạn của bằng chứng

Sensor `saber-native-v1` đo các thao tác cố định do executor thực hiện:

| Bản ghi | Dữ liệu lấy từ thực thi |
|---|---|
| `process.start` | PID do OS cấp khi tạo process, PID cha, command line đã chạy |
| `dns.response` | Phản hồi DNS A nhận qua UDP, tên `lab.saber.test`, địa chỉ và cổng resolver |
| `network.connect` | Socket TCP đã kết nối, địa chỉ/cổng nguồn và đích lấy từ socket |
| `http.response` | HTTP status, số byte phản hồi, thời gian request |
| `file.write` | File `workloads/<actor>/last-action.json` đã ghi và fsync |
| `file.read` | Số byte và SHA-256 từ nội dung đọc lại, so sánh với dữ liệu vừa ghi |
| `process.exit` | Exit code thực, loại lỗi nếu có |

DNS responder và HTTP service bind loopback với cổng do OS cấp. DNS là trao đổi gói
UDP thật với resolver nội bộ; không phải log truy vấn Internet hay DNS của toàn máy.
File hiện tại là receipt chứa event ID/status, **không phải mọi tài liệu của người dùng**.
Các sự kiện chỉ được ghi sau khi thao tác tương ứng hoàn thành. Khi lỗi xảy ra, chuỗi
có thể thiếu bước; không tự điền bản ghi thành công. Timeout có thể mất các bước worker
chưa trả về, khi đó không được suy luận thao tác ứng dụng chưa xảy ra.

Đây là instrumentation của workload có kiểm soát, **chưa phải Sysmon, ETW, auditd,
eBPF hay PCAP**. Không thu được tiến trình lạ, shell tùy ý, registry, mọi thay đổi file
hoặc traffic ngoài worker. Process con không phải ranh giới bảo mật giữa agents:
profile local dùng quyền người chạy; sandbox/VM bao quanh toàn world. Red vẫn thử
điểm yếu của ứng dụng lab; `register_job`, `disrupt` và containment chưa biến thành
persistence, DoS hay firewall trên OS. Không được kết luận có xâm nhập OS từ log này.

Mỗi capture có `capture_id`, thời gian UTC, `actor_id`, tick, PID và `event_id` ứng dụng.
Nếu không xác nhận được event ID thì để null. Worker lỗi sau khi server đã xử lý sẽ
giữ event ID nếu đã nhận được; executor dừng và **không tự retry** thao tác.
HTTP 403 với process exit 0 nghĩa là request đã hoàn tất nhưng ứng dụng từ chối.

Blue nhận tối đa 35 bản ghi gần nhất trong `observe.native_telemetry`, không có nhãn
red/client của actor, kế hoạch riêng hay evaluator effects. Dùng `event_id` để liên
kết bằng chứng ứng dụng/case; số `id` của log native thuộc bảng khác. Baseline hiện vẫn
phân tích application events; chưa có detection engine OS riêng hoặc rule Sysmon.

## Chạy và xem

Tại root repo, tạo world **mới**:

```powershell
uv run saber world init --out runs/native-world --clients 4 --execution native
uv run saber world run --out runs/native-world --ticks 18
node agent-office/bin/agent-office.js watch --world runs/native-world --open
```

Trong Office, bấm robot/màn hình/thẻ của một agent, mở **Process · File · DNS · Network**.
Mỗi agent có cửa sổ 100 bản ghi riêng, không chia sẻ giới hạn 200 application events của
toàn world. Bỏ chọn “Lịch sử riêng của agent” để lọc theo thao tác đang chọn; mở từng
dòng để xem các trường chi tiết. Nếu thao tác đã ra ngoài cửa sổ native thì giao diện
báo thiếu dữ liệu, không dựng lại lịch sử. Đây là log, không phải video desktop.

Viewer phải là bản mới và chạy bằng `watch --world` hoặc `watch --bundle` để đọc file
native. `run`/`serve` nhận snapshot qua HTTP chưa tự tải thêm cửa sổ native từ runtime.
Với VM đồng bộ file về máy xem, cần cả `office.json` và thư mục `native-office/` của
cùng world. Không cần đồng bộ database, keys hoặc dữ liệu evaluator.

Chạy liên tục trong terminal khác:

```powershell
uv run saber world run --out runs/native-world --forever
# Dừng từ terminal thứ ba; sau STOP cần --resume để chạy tiếp
uv run saber world stop --out runs/native-world
uv run saber world run --out runs/native-world --forever --resume
```

Gemini vẫn độc lập với chế độ execution. Nếu muốn bật, thêm các cờ đã có
`--llm --key-pool keys_pool.txt --call-budget 200` vào `world run`; budget là tổng
HTTP attempts tích lũy của world, không reset khi resume. Worker không được cấp key
Gemini; capability ứng dụng riêng được chuyển qua stdin, không nằm trong command
line/log. Không xuất HTTP headers, body, biến môi trường, prompt hoặc API keys.

Không đổi `execution_mode` của checkpoint đã chạy. World cũ không có bằng chứng
OS/network để bổ sung ngược; chọn thư mục mới. Các phép thử native không cần gọi LLM.

## Lịch sử, dung lượng và xuất log

```powershell
# 100 bản ghi gần nhất của một agent, mỗi dòng một JSON
uv run saber world native-logs --out runs/native-world --actor client-1 --limit 100
# Trang trước: lấy ID nhỏ nhất của trang vừa xem làm --before
uv run saber world native-logs --out runs/native-world --actor client-1 --before 101
```

`native_events` trong `world.sqlite3` lưu lịch sử đầy đủ của lần thực thi đã ghi nhận;
lệnh trên mở DB read-only. `native.jsonl` là bản xuất xoay vòng 5 MB × tối đa 4 file,
có thể dùng làm đầu vào collector do người vận hành cấu hình; chưa tự gửi vào SIEM.
`native-office/<actor>.json` là cửa sổ public 100 bản ghi, không phải archive.

Native history hiện chưa archive/prune riêng trong SQLite. Dữ liệu native tính vào
`disk_budget_bytes`; mặc định 512 MB cho cả world. Chạm budget thì world dừng, không
xóa bằng chứng để chạy tiếp. `--forever` không có nghĩa dung lượng lưu trữ vô hạn.
Mỗi lượt spawn process nên tick thực tế có thể chậm hơn `tick_seconds`, đặc biệt trên
Windows hoặc với nhiều agents. Scheduler hiện thực thi các lượt tuần tự; không giữ
200 process đồng thời. Số liệu CPU/RAM dài hạn cần đo theo roster và môi trường thực.

## Sandbox và VM

```powershell
uv run saber env init --profile sandbox --execution native --out runs/env-native.json
uv run saber env render --config runs/env-native.json --out runs/native-bundle
uv run saber env up --bundle runs/native-bundle
node agent-office/bin/agent-office.js watch --bundle runs/native-bundle --open
```

Sandbox scripted dùng `network_mode: none`; loopback DNS/TCP vẫn chạy trong container.
Với VM/remote, chọn profile tương ứng rồi chuyển bundle và chạy trong guest như
[hướng dẫn môi trường](ENVIRONMENTS_VI.md). Native mode không yêu cầu root, quyền
ptrace, Docker socket trong container hay mở cổng ra host.

Đã kiểm chứng process/file/DNS/TCP thật trên Windows local bằng tests và demo 11 agents,
18 tick, 162 thao tác, 1.134 bản ghi native. Chrome kiểm tra cửa sổ client/red/blue và
lọc theo event. Docker Engine trên máy phát triển chưa chạy, nên **chưa kiểm chứng
native workload trong Linux container/VM**; kiểm tra schema/bundle không thay cho chạy thật.

Artifact local: `runs/world-native-demo/`, `runs/native-office-check/verification.json`
và ảnh `client-native.png`, `red-native.png`, `blue-native.png`. Demo đã dừng, dùng
scripted, không tiêu thụ Gemini. Catalog và trạng thái `DEV_SIMULATION_ONLY` giữ nguyên.
