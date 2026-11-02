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
- Blue mặc định gồm lead/monitor/hunter/DFIR/content/IR; `world init --blue-specialists`
  bổ sung malware/network/intel/platform/identity/recovery. Có case chung, giao việc, timeline từ
  evidence ID, rule có schema giới hạn, sửa kiểm soát truy cập, containment theo bằng
  chứng, quarantine/rollback job, khôi phục dịch vụ, cảnh báo người dùng và đóng case.
- Đóng case resolved yêu cầu kết quả thực thi đã xác minh và biện pháp vẫn có hiệu lực;
  đóng FP cần finding có dẫn chứng. Không đóng khi còn task chưa giải quyết. Điểm
  phát hiện không được dùng thay cho bằng chứng containment. Chặn nhầm client làm
  request của client bị từ chối thật và được tính vào tác động vận hành.
- Chạy theo tick với thứ tự actor luân phiên; mỗi actor có nhịp riêng. LLM chạy trong
  hàng đợi worker nền, nên request chậm không giữ vòng hoạt động client. Đây là lịch
  thực thi xen kẽ trên ứng dụng chung, không phải mỗi agent là một VM/OS riêng.
- Checkpoint, STOP, khóa một writer, JSONL xoay vòng, archive bằng chứng, ngân sách đĩa,
  giới hạn LLM lưu bền và supervisor khởi động lại worker khi lỗi.

[Hướng dẫn SOC specialists](SOC_SPECIALISTS_VI.md) mô tả actor kiêm nhiệm, truy vấn log
phân trang, task nhận việc/bàn giao, notebook bền, `wait`/`finish`, artifact, rule testing
và kiểm tra phục hồi. `world actor-resume` cho phép operator tiếp tục actor đã dừng;
lệnh này yêu cầu world không đang chạy. Resume process không tự resume actor đã finish.

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

Model mặc định của `world` là `gemini-3.5-flash-lite`; có thể chọn model khác qua `--model`.
Kiểm tra API thật ngày 2026-11-01 phát hiện một số project trong pool trả 404 với
`gemini-2.5-flash`: model này chỉ còn phục vụ người dùng đã sử dụng trước đó, không
mở cho người dùng mới. Đây không phải lỗi hết quota và không tự chứng minh key hỏng.
Xem [chính sách model của Google](https://ai.google.dev/gemini-api/docs/deprecations).

Để kiểm tra API thật với ba agent và chỉ in số thứ tự key/mã HTTP/counters:

```powershell
.\.venv\Scripts\python.exe scripts/smoke_world_gemini.py --live --out runs\gemini-live-check --call-budget 12
```

Lệnh yêu cầu thư mục mới, giới hạn tối đa 12 lượt gọi và tự dừng. Hai vòng chạy kiểm
tra restart và chuyển key bằng trần cục bộ **riêng cho bài thử** là 1 lượt/key/ngày;
không cố làm cạn quota Google. `--rounds 1` chỉ chạy một vòng. Bằng chứng lưu trong
`live-check.json`, cùng report và telemetry lab. HTTP 200 và agent thực thi kế hoạch
là hai điều kiện riêng; `engine=hybrid` hay việc liệt kê được model chưa đủ xác nhận.

Kết quả kiểm tra thật ngày 2026-11-01: `gemini-3.5-flash-lite` trả HTTP 200 cho cả
6/6 lượt, 9 hành động do LLM chọn được thực thi thành công qua HTTP trong lab.
Sau restart, key chuyển client 1→2, red 201→202, blue 401→402. Bằng chứng cục bộ:
`runs/live-gemini-35-lite-check-20261101/live-check.json`. Bài thử `gemini-3.8-flash`
trước đó gặp 503/lỗi transport, nên không dùng làm mặc định. Đây là kết quả mẫu,
không phải kiểm tra toàn bộ 602 key hoặc bằng chứng quota Google đã cạn.

### Ba hàng đợi key riêng cho client / red / blue

Khi bật `--llm`, mặc định `--key-layout teams` chia theo thứ tự key trong file:

| Đội | Vị trí key (đếm từ 1) | Số lượng với file 602 key |
|---|---|---|
| Client | 1–200 | 200 |
| Red | 201–400 | 200 |
| Blue | 401 đến cuối file | 202 |

Mỗi đội giữ key đang active cho đến khi chạm giới hạn cục bộ hoặc gặp lỗi quota/API,
rồi chọn key kế tiếp còn khả dụng trong **chính pool của đội đó**. Key bị `429` nghỉ
theo cooldown và có thể dùng lại sau khi hồi quota. Vị trí active được lưu bằng
fingerprint, nên restart tiếp tục đúng hàng đợi mà không lưu key thật vào database.
Nếu cả pool của một đội hết, suy luận của đội đó chờ đợt lập kế hoạch tiếp theo;
baseline scripted tiếp tục chạy và hai đội còn lại vẫn dùng pool của mình. Không
mượn key chéo đội.

Một yêu cầu suy luận thử tối đa 3 key khi gặp lỗi có thể chuyển tiếp; nếu vẫn thất
bại, lần lập kế hoạch sau tiếp tục từ vị trí đã lưu. Dừng runner sẽ ngăn phát sinh
thêm lượt thử mới. Tất cả lượt thử vẫn tính vào `--call-budget` **chung cho toàn world**:
`200` là 200 lượt API tổng, không phải 200 lượt/key hoặc mỗi đội.

Không cần đổi lệnh đã hướng dẫn để bật cách chia này. Có thể ghi rõ:

```powershell
.\.venv\Scripts\python.exe -m saber.cli.main world supervise --out runs\world-gemini --llm --key-pool keys_pool.txt --key-layout teams --call-budget 200
```

`report.json` có `llm_pools.client/red/blue` (dải key, vị trí active, trạng thái), và
`llm.by_team` (attempts/successes/token theo đội). Chỉ hiện số thứ tự, không hiện key.
`--client-keys` và `--red-keys` đổi kích thước hai phần đầu nếu cần; blue nhận phần còn
lại. `--key-layout shared` chọn lại pool chung cũ, hữu ích khi chỉ có ít key.

Dòng trống và comment `#` không được tính vào vị trí; hỗ trợ `NAME=key` và UTF-8 BOM.
Ở chế độ `teams`, file phải có ít nhất 401 key duy nhất với cấu hình mặc định. Key
trùng bị báo lỗi trước khi gọi API để không âm thầm dịch ranh giới 200/400 hoặc dùng
chung một key giữa hai đội. File gốc không bị sửa, sao chép hay tách thành ba file.

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

Index là vị trí zero-based của key sau khi bỏ dòng trống/comment (`teams` yêu cầu
key duy nhất; `shared` loại key trùng như trước). Mapping giúp gộp quota, không
chứa key. Giữ alias ổn định giữa các lần chạy. Key không được lưu trong DB, log, prompt,
viewer hay filesystem của ứng dụng lab; DB chỉ giữ fingerprint và counters.

`profile_refresh_ticks` điều chỉnh khoảng lập kế hoạch; `llm_workers` mặc định 4,
tối đa 16. Mỗi plan tối đa 4 hành động và luôn bị kiểm tra quyền khi thực thi. Khi
plan hết, model lỗi hoặc hết budget, baseline scripted tiếp tục hoạt động và nguồn
quyết định được ghi rõ (`llm` / `scripted` / `scripted-fallback`). Plan quá cũ bị bỏ.
Không được gọi kết quả HYBRID là kết quả LLM thuần.

## Quan sát bằng agent-office

Skills của các vai và kiểm tra cách nạp được mô tả trong
[hướng dẫn skills](SKILLS_VI.md). Khi bật model, world dùng entrypoint theo vai và
hợp đồng application lab; `observation.tools` vẫn quyết định quyền thực tế. Scripted
policy không gọi model. Thiếu/hỏng skill không được tự thay thành specialist rỗng.

Runtime ghi snapshot `office.json` mỗi tick, lúc khởi động và lúc dừng. Xem world
đang chạy hoặc đã dừng từ một terminal riêng (Node.js 18+, không cần npm install):

```powershell
node agent-office/bin/agent-office.js watch --world runs/world --open
```

Hoặc khởi động world qua viewer để nhận snapshot trực tiếp:

```powershell
node agent-office/bin/agent-office.js run -- .venv/Scripts/python.exe -m saber.cli.main world run --out runs/world --forever
```

Hoặc chạy `agent-office serve` rồi thêm `--office-url http://127.0.0.1:7788` vào
`world run`. Không suy ra API calls từ số lần agent xin plan: usage lấy từ ledger
provider. Roster có lọc đội/phân trang; từng agent hiển thị nguồn hành động, HTTP
status và tick cuối. Quota chỉ hiển thị số thứ tự key, không raw key hay prompt.

Sandbox dùng `watch --bundle PATH_TO_BUNDLE` trên Docker host, không mở network
container. VM/server dùng `watch --world` tại máy đích và SSH forward cổng viewer.
Chi tiết trạng thái heartbeat, STOP/resume và cách đọc counter ở
[Agent Office README](../agent-office/README.md).
Viewer không được cấp quyền đọc database hay ground truth.

## Dữ liệu và đánh giá

| File | Nội dung |
|---|---|
| `config.json` | Danh sách actor và cấu hình đã chọn |
| `world.sqlite3` | Trạng thái kiểm soát, case, telemetry, memory riêng và ledger evaluator |
| `access.jsonl`, `.1`–`.3` | Telemetry công khai từ thao tác đã thực thi, tối đa khoảng 20 MB |
| `report.json` | Báo cáo cho operator; không đưa vào observation của agent |
| `office.json` | Snapshot operator cho Agent Office; roster, counter và chỉ số quota |
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
