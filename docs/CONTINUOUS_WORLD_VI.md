# SABER Continuous World — client / red / blue cùng hoạt động

Triển khai ngày 2026-11-01. Lệnh mới: `saber world`. Runtime này bổ sung môi trường
hoạt động lâu dài; các lệnh benchmark `task`, `soc`, `range`, `population` cũ vẫn giữ
nguyên hợp đồng. Trạng thái nghiên cứu vẫn là `DEV_SIMULATION_ONLY`, 0 `READY_BENCHMARK`.

## Đã có gì

- Một ứng dụng lab HTTP thật, chỉ bind `127.0.0.1`, với danh tính và bearer capability
  riêng cho từng agent. Tài khoản, tài liệu, phiên đăng nhập, job và trạng thái dịch vụ
  nằm trong SQLite; các nhóm sử dụng cùng một môi trường.
- Client có vai và mục tiêu tùy chỉnh: người dùng thường, nhân viên, developer, admin…
  Có đăng nhập/nhập nhầm, tìm kiếm, đọc/ghi tài liệu, sử dụng ứng dụng, bảo trì, nhận và
  xác nhận cảnh báo. Người dùng chỉ thấy lỗi hoặc thông báo thực sự gửi tới mình.
- Red có các vai recon/access/impact: khám phá liên kết, thử quyền đọc tài liệu, lưu bản
  sao dữ liệu đã thực sự đọc vào kho trong lab, đăng ký automation và gây lỗi dịch vụ
  có thời hạn. Các agent trao đổi phát hiện qua kênh riêng của đội.
- Blue gồm lead/monitor/hunter/DFIR/content/IR. Có case chung, giao việc, timeline từ
  evidence ID, rule có schema giới hạn, sửa kiểm soát truy cập, containment theo bằng
  chứng, quarantine/rollback job, khôi phục dịch vụ, cảnh báo người dùng và đóng case.
- Đóng case yêu cầu kết quả thực thi đã xác minh và biện pháp vẫn có hiệu lực. Điểm
  phát hiện không được dùng thay cho bằng chứng containment. Chặn nhầm client làm
  request của client bị từ chối thật và được tính vào tác động vận hành.
- Chạy theo tick với thứ tự actor luân phiên; mỗi actor có nhịp riêng. LLM chạy trong
  hàng đợi worker nền, nên request chậm không giữ vòng hoạt động client. Đây là lịch
  thực thi xen kẽ trên ứng dụng chung, không phải mỗi agent là một VM/OS riêng.
- Checkpoint, STOP, khóa một writer, JSONL xoay vòng, archive bằng chứng, ngân sách đĩa,
  giới hạn LLM lưu bền và supervisor khởi động lại worker khi lỗi.

## Chạy nhanh trên máy này

Từ thư mục repo, dùng môi trường `.venv` đã có:

```powershell
.\.venv\Scripts\python.exe -m saber.cli.main world init --out runs\world --clients 12
.\.venv\Scripts\python.exe -m saber.cli.main world run --out runs\world --ticks 60
```

Lần khởi tạo tạo `runs/world/config.json`. Trước lần chạy đầu, có thể sửa danh sách
`actors`: thêm nhiều agent cùng vai, thay `goal`, tên client `role` bất kỳ và
`interval_ticks`. Ví dụ có thể thêm một client vai `student` hoặc thêm hai `dfir`.
Vai red/blue phải thuộc tập công cụ đã triển khai. Cấu hình được đóng băng sau lần
chạy đầu để resume không vô tình đổi danh tính, chính sách hay seed; muốn cấu hình
khác dùng thư mục world mới. Trường mới có giá trị mặc định được chuẩn hóa khi đọc
checkpoint cũ.

Chạy lâu dài có restart khi worker lỗi:

```powershell
.\.venv\Scripts\python.exe -m saber.cli.main world supervise --out runs\world
```

Supervisor có tối đa 3 lần restart với backoff; dừng sau lỗi lặp lại thay vì tạo vòng
lặp lỗi vô hạn. Nó không đăng ký Windows service/Task Scheduler và không tự chạy sau
khi máy khởi động lại. Chạy lại cùng lệnh sẽ tiếp tục checkpoint. Nếu chỉ cần một
process foreground: `world run --out runs\world --forever`.

Dừng từ terminal khác, xem báo cáo hoặc tiếp tục sau STOP:

```powershell
.\.venv\Scripts\python.exe -m saber.cli.main world stop --out runs\world
.\.venv\Scripts\python.exe -m saber.cli.main world status --out runs\world
.\.venv\Scripts\python.exe -m saber.cli.main world supervise --out runs\world --resume
Get-Content runs\world\access.jsonl -Wait -Tail 15
```

Không xóa STOP tự động khi crash restart. Ctrl+C dừng có kiểm soát. Khi đang có request
LLM, shutdown chờ request đang chạy kết thúc (transport timeout 60 giây).

## Kết nối pool Gemini

Mặc định là **SCRIPTED**: không đọc key, không gọi model. Bật **HYBRID** bằng lệnh
explicit có giới hạn số lượt HTTP. Ví dụ dưới đây cho phép tối đa 200 lượt trong
toàn bộ vòng đời world, bao gồm các lần khởi động lại:

```powershell
.\.venv\Scripts\python.exe -m saber.cli.main world supervise --out runs\world --llm --key-pool keys_pool.txt --call-budget 200
```

`--llm` dùng billing/quota đang tồn tại trên project; chương trình không bật billing
hay đổi tier. `--call-budget` là trần lượt thử HTTP, không phải trần tiền USD và không
khẳng định mọi project đều miễn phí. Nâng giá trị này là quyết định của người vận hành.

Scheduler có các trần cục bộ `--project-rpm` (mặc định 2), `--project-rpd` (20, cửa sổ
24 giờ trượt), `--project-tpm` (100000). Đây là **giới hạn do ứng dụng đặt**, không phải
quota Google được bảo đảm. Token được dự trữ bảo thủ theo độ dài prompt cộng output
cap; usage thật được lưu riêng trong report. `429` được nghỉ ít nhất 60 giây hoặc theo
`retryDelay` dài hơn; lỗi mạng/5xx được nghỉ tạm thời; 401/403/404 vô hiệu hóa key/project
cho model đó. Không liên tục thử lại project đang nghỉ.

Với một key trên mỗi project như pool đã mô tả, không cần mapping thêm. Nếu nhiều key
thuộc cùng project, truyền `--project-map config/project-map.json`, nội dung ví dụ:

```json
{"0": "project-a", "1": "project-a", "2": "project-b"}
```

Index là vị trí zero-based **sau khi loại key trùng**. Mapping giúp gộp quota, không
chứa key. Giữ alias ổn định giữa các lần chạy. Key không được lưu trong DB, log, prompt,
viewer hay filesystem của ứng dụng lab; DB chỉ giữ fingerprint và counters.

`profile_refresh_ticks` điều chỉnh khoảng lập kế hoạch; `llm_workers` mặc định 4,
tối đa 16. Mỗi plan tối đa 4 hành động và luôn bị kiểm tra quyền khi thực thi. Khi
plan hết, model lỗi hoặc hết budget, baseline scripted tiếp tục hoạt động và nguồn
quyết định được ghi rõ (`llm` / `scripted` / `scripted-fallback`). Plan quá cũ bị bỏ.
Không được gọi kết quả HYBRID là kết quả LLM thuần.

## Quan sát bằng agent-office

Runtime phát sự kiện agent/tool/status/LLM trực tiếp tới viewer hiện có:

```powershell
node agent-office/bin/agent-office.js run -- .venv/Scripts/python.exe -m saber.cli.main world run --out runs/world --forever
```

Hoặc chạy viewer riêng rồi thêm `--office-url http://127.0.0.1:7788` vào `world run`.
Viewer không được cấp quyền đọc database hay ground truth.

## Dữ liệu và đánh giá

| File | Nội dung |
|---|---|
| `config.json` | Danh sách actor và cấu hình đã chọn |
| `world.sqlite3` | Trạng thái kiểm soát, case, telemetry, memory riêng và ledger evaluator |
| `access.jsonl`, `.1`–`.3` | Telemetry công khai từ thao tác đã thực thi, tối đa khoảng 20 MB |
| `report.json` | Báo cáo cho operator; không đưa vào observation của agent |
| `runtime.json` | Trạng thái process và địa chỉ loopback, không chứa bearer token |
| `sealed-archives/` | Các cặp event/effect nén, có hash trong DB, chỉ cho evaluator/operator |

SQLite là nguồn ghi nhận chính. JSONL là bản xuất thuận tiện để tail; sau crash giữa
ghi file và checkpoint có thể lặp event ID, nên consumer phải deduplicate theo `id`.
Events cũ vượt `retention_events` được archive trước khi bỏ khỏi bảng đang hoạt động;
case giữ snapshot bằng chứng của chính nó. Agent không có endpoint đọc archive hoặc
report, không có quyền truy vấn tương lai hoặc chọn principal khác.

Report đo request thành công/thất bại của client, truy cập trái quyền, số byte thực sự
sao chép trong lab, job trái quyền, outage ticks, phát hiện theo evidence, độ trễ phát
hiện/phản ứng theo tick, phản ứng được xác minh và false containment. Truth suy từ
quyền sở hữu dữ liệu và thay đổi trạng thái thực thi, không từ lời khai red/blue.
Các chỉ số là mức **sự kiện/case của ứng dụng lab**, không phải kết quả tổng quát cho
175 subtasks hoặc chứng minh multi-agent tốt hơn single-agent.

## Phạm vi đã thực thi và phần mở rộng

Web hiện là website/ứng dụng nội bộ giả lập với request HTTP và thay đổi dữ liệu thật.
Chưa có browser desktop, VM Windows/Linux riêng cho từng client, Internet browsing,
thực thi shell, mã độc, Ghidra/IDA hay tích hợp SIEM production. Job red là đăng ký
trong kho ứng dụng, không phải persistence hệ điều hành; gián đoạn là lỗi dịch vụ có
thời hạn, không phải packet flood. Collection sao chép dữ liệu mồi vào kho nội bộ,
không có endpoint exfil ra Internet.

Các khả năng OS/VM/web ngoài cần adapter riêng với kiểm soát phạm vi và isolation;
không mở rộng quyền của các tool hiện tại thành shell hay URL tùy ý. Runtime mới là
nền chạy chung để gắn những adapter đó, giữ riêng evaluator và bộ credential LLM.

## Kiểm thử

```powershell
.\.venv\Scripts\python.exe -m pytest tests/world
.\.venv\Scripts\ruff.exe check src tests scripts
.\.venv\Scripts\mypy.exe
```

Test gọi HTTP loopback thật và dùng transport LLM giả, không dùng key thật. Kiểm tra
truy cập âm thầm, sao chép bytes thực, chặn/khôi phục/quarantine, false containment,
không rò truth, cô lập hai world, action ngoài quyền, resume, lock Windows, STOP,
archive, LLM không chặn client và quota bền vững.

Kết quả kiểm tra tại lần triển khai này (Windows, 2026-11-01): **1.262 tests pass**,
trong đó 32 tests cho `world`; có 7 subtests pass và một cảnh báo deprecation từ
Starlette/httpx. Lint, mypy và format check đã chạy. Các file cũ được formatter chỉnh
đã được so sánh AST trước/sau, không thay đổi cấu trúc chương trình.

Demo cục bộ `runs/world-demo`: 8 client + 3 red + 6 blue, 466 tick, 7.214 thao tác,
55 case và 61 phản ứng xác minh. Đã chạy qua supervisor, dừng bằng STOP và resume
thêm 3 tick với cùng `world_id`. Đây là baseline scripted, không phải phép đo năng
lực LLM; không gọi Gemini thật hoặc dùng quota của pool trong quá trình kiểm thử.
