# agent-office

Viewer 3D cho các agent. Với SABER continuous world, viewer nhận roster và số liệu
từ runtime, kể cả khi chạy scripted và không gọi LLM. Cần **Node.js 18+** trên máy
mở viewer; bản HTML đã build sẵn, không cần `npm install` để xem.

## Xem SABER world hiện tại

Chạy từ thư mục gốc repo, ở terminal riêng:

```powershell
node agent-office/bin/agent-office.js watch --world runs/world --open
```

Thay `runs/world` bằng đúng thư mục `--out` của runtime. Lệnh này xem world đang chạy
hoặc đã dừng; không khởi động agent, không gọi Gemini. Mở URL được in ra, mặc định
`http://127.0.0.1:7788`. Nếu cổng bận, viewer thử cổng tiếp theo. Ctrl+C dừng viewer.

| Môi trường | Lệnh / vị trí chạy viewer |
|---|---|
| Local | `node agent-office/bin/agent-office.js watch --world runs/world` |
| Sandbox | `node agent-office/bin/agent-office.js watch --bundle runs/my-sandbox` trên Docker host |
| VM tự dựng | `watch --world PATH_TO_WORLD` trong VM có Node.js |
| Server lab | `watch --world PATH_TO_WORLD` trên server có Node.js |

Sandbox lấy `/data/office.json` bằng `docker cp`, chọn đúng container theo Compose
project của bundle. Không mở cổng container, không đổi `network_mode: none`, không
đọc key mount. Cần Docker daemon và container đã được tạo; container đã dừng vẫn đọc
được, nhưng `env down` xóa container thì cần `env up` lại. Bundle cũ cần runtime mới
để sinh `office.json`; bản export mới kèm viewer bên ngoài Docker build context.

Với VM/server, truy cập viewer loopback qua SSH tunnel trên máy của bạn:

```bash
ssh -N -L 7788:127.0.0.1:7788 user@lab-host
```

Thay cổng đích bằng cổng viewer thực tế. Hoặc đồng bộ **chỉ `office.json`** về một
thư mục local rồi dùng `watch --world` với thư mục đó.

Có thể khởi động world và nhận snapshot trực tiếp trong một lệnh:

```powershell
node agent-office/bin/agent-office.js run -- .venv/Scripts/python.exe -m saber.cli.main world run --out runs/world --forever
```

`run` đặt `AGENT_OFFICE_URL` cho runtime. Với viewer `serve` có sẵn, dùng
`world run --office-url http://127.0.0.1:7788`. Gemini dùng snapshot trực tiếp,
không đi qua proxy OpenAI/Anthropic. Các cờ `--llm`, `--key-pool`, `--call-budget`
thuộc lệnh SABER sau `--`; xem [hướng dẫn world](../docs/CONTINUOUS_WORLD_VI.md).

## Đọc giao diện world

World tạo bằng `--execution native` có thêm **Process · File · DNS · Network** khi
bấm agent. Viewer `watch` đọc 100 bản ghi riêng từ `native-office/<actor>.json`,
local hoặc `docker cp` từ sandbox; không đọc key hay DB evaluator. Mở từng dòng để
xem PID/command line, DNS, socket, file hash và exit code. Bỏ checkbox lịch sử riêng
để lọc theo application event đang chọn. Các mục đã mở được giữ khi cập nhật live.
Sensor chỉ đo workload cố định, chưa giám sát toàn OS. [Hướng dẫn native](../docs/NATIVE_TELEMETRY_VI.md).

Nếu đồng bộ snapshot từ VM, cần thêm thư mục `native-office/` cùng world để xem mục
này. `run`/`serve` hiện chỉ nhận snapshot, chưa tự tải cửa sổ native. Backend Node cũ
cần restart sau cập nhật code; refresh trình duyệt chỉ nạp lại phần giao diện.

- Chọn world, lọc Clients/Red Team/Blue Team; hỗ trợ roster tối đa 200 agent.
  Ba đội ngồi trong ba khu riêng: Clients xanh ngọc, Red Team đỏ, Blue Team xanh dương.
  Bàn có mã C01…C24 / R01…R24 / B01…B24, hiển thị trên thẻ agent.
- Chọn **Số bàn mỗi đội**: 12 (36 slots, mặc định) hoặc 24 (72 slots). Mỗi lượt xem
  lấy tối đa số bàn đã chọn **từ từng đội**, nên client đông không đẩy red/blue ra
  khỏi trang đầu. Mũi tên chuyển nhóm tiếp theo của từng đội; đội đã hết người ở trang
  đó có thể trống. `72/200` nghĩa là 72 agent đang hiển thị trong roster 200.
- Các nút **Toàn cảnh / Clients / Red Team / Blue Team** phía trên đổi góc nhìn camera.
  Bộ lọc đội trong sidebar đổi các agent đang hiển thị và nhìn gần khu đó. Lọc đội
  vẫn giữ agent trong đúng khu; không chuyển blue sang bàn client. Biển khu ghi số
  đang thấy/tổng số hoặc “ẩn theo bộ lọc”. Bàn trống không đại diện cho một agent.
- Thêm slots chỉ đổi bố cục viewer; không tăng số agent, worker hay budget của runtime.
  Để thay roster, chỉnh cấu hình world trước lần chạy đầu theo [notes](../notes.md).
- Dòng “học” cho biết số lượt tổng kết / đề xuất / bản phát hành của actor. Phát hành
  không đồng nghĩa đã đổi bản trong case đang chạy; xem epoch ở `world learning status`.
  Không xuất nội dung notebook, bài học hay đáp án replay lên viewer.
- Mỗi actor hiện chuyên môn đã cấu hình, chuyên môn/task đang xử lý và số task
  offered/active/blocked/done. `WAITING` hiện tick thức dậy; `DONE` giữ idle dù request
  suy luận cũ chưa về. Đây là trạng thái actor, khác trạng thái dừng của cả world.
  Snapshot cũ thiếu các trường này vẫn hiển thị được với giá trị mặc định.
- Profile `local/sandbox/vm/remote` là nơi triển khai được khai báo. `Scripted` dùng
  hành vi có sẵn; `Gemini + fallback` có suy luận bất đồng bộ và fallback scripted.
- Tổng LLM attempts, successes và token lấy từ ledger provider của world, cộng dồn
  qua resume. Hàng đợi suy luận không được tính thành một API attempt. Quota và usage
  là theo đội; không tự chia token cho từng agent.
- Key hiển thị **số thứ tự** trong pool đã loại trùng: client 1–200, red 201–400,
  blue phần còn lại theo cấu hình. `ready`, `in_flight`, `cooling_down`,
  `at_local_limit`, `disabled`, `waiting_for_quota` là trạng thái ghi nhận gần nhất;
  viewer không thử key hay kiểm chứng quota Google.
- Mỗi agent có tool cuối, HTTP status, tick và nguồn `llm`, `scripted` hoặc
  `scripted-fallback`. “Hoạt động tick” gồm agent vừa có hành động hoặc chờ suy luận;
  hoạt ảnh 3D chỉ minh họa. Log bên phải theo trang đang xem, giữ tối đa 200 dòng.
- Bấm **robot, màn hình/bàn hoặc thẻ agent** để mở bảng chi tiết. Có thể dùng Tab +
  Enter trên thẻ; Escape hoặc nút Đóng để quay lại. Bảng áp dụng cho cả client/red/blue.
- `viewer online` chỉ xác nhận trình duyệt nối được viewer. Runtime có trạng thái
  riêng: đang chạy, đã dừng, hoặc mất cập nhật/chưa rõ. Mất heartbeat quá
  `max(30 giây, 3 × tick_seconds + 5 giây)` được đánh dấu cũ. Watch đọc mỗi 2 giây.

`office.json` được ghi nguyên tử khi khởi động, sau mỗi tick và lúc dừng; chứa roster,
counter, chỉ số quota và trace thao tác đã lọc. Không chứa raw key, bearer, prompt, nội dung tài liệu hay
plan riêng. Đây là màn hình **operator**, không cấp endpoint này cho agent. `watch`
chỉ đọc, tắt proxy/ingest; không điều khiển world, SIEM/SOAR hay desktop máy thật.
Nếu xem world cũ không có snapshot, chạy/resume bằng code mới. Khi render bundle mới,
giữ nguyên dữ liệu cũ và làm theo [hướng dẫn môi trường](../docs/ENVIRONMENTS_VI.md).

## Bấm vào red team để xem tấn công và phản ứng blue

1. Chọn đúng world, lọc **Red Team**, bấm agent như `red-access` hoặc `red-impact`.
2. Bấm một dòng trong **Diễn biến** để xem event ID, tick, nguồn quyết định và sơ đồ
   **agent → công cụ → mục tiêu**, kèm HTTP status. Nút **Mới nhất** theo thao tác mới
   nhất của agent; chọn một event cụ thể sẽ giữ lựa chọn khi snapshot tiếp theo tới.
3. Checkbox **Kèm sự kiện liên quan qua case / mục tiêu** bật các sự kiện có liên kết
   bằng chứng, cùng case hoặc nhắm trực tiếp tài khoản của agent. Không ghép sự kiện
   chỉ vì cùng tick hoặc cùng tên dịch vụ.
4. **Case và phản ứng phòng thủ** hiển thị event bằng chứng và các phản ứng đã ghi nhận
   trong case, ví dụ `quarantine`, `contain`, `restore`. Bấm số event để xem chi tiết.

HTTP 200/201 chỉ xác nhận yêu cầu thành công; không tự kết luận xâm nhập thành công.
Dòng “Thay đổi đã được xác minh lúc thực thi” lấy từ kết quả phản ứng của runtime,
không khẳng định biện pháp vẫn có hiệu lực ở tick hiện tại. Trạng thái case là ghi
nhận của blue, không xuất ground truth của evaluator. Trace không có raw arguments,
response body, notebook hay nội dung trao đổi riêng. Nguồn `unknown` nghĩa là không
có journal xác nhận nguồn quyết định; không tự gán direct HTTP cho LLM.

Cửa sổ chứa tối đa **200 event gần nhất toàn world**, **12 case liên quan**,
**50 evidence IDs đang có trong cửa sổ/case** và **8 phản ứng cuối/case**. Bảng ghi rõ
số dữ liệu đang xem; event bị xoay khỏi cửa sổ sẽ báo không còn thay vì thay bằng event
khác. Xem toàn bộ lịch sử bằng log/database/archive của world theo quyền operator.
Snapshot cũ vẫn xem được roster và báo chưa có trace; cần chạy/resume với code mới
để sinh trace. Watch không sửa database hay tự chạy world.

Demo scripted có sẵn trên máy phát triển trong `runs/office-inspector-demo`:

```powershell
node agent-office/bin/agent-office.js watch --world runs/office-inspector-demo --open
```

Nếu chưa có demo, tạo thư mục mới và chạy 18 tick, không cần Gemini:

```powershell
uv run saber world init --out runs/my-inspector-demo --clients 2 --tick-seconds 0.1
uv run saber world run --out runs/my-inspector-demo --ticks 18
node agent-office/bin/agent-office.js watch --world runs/my-inspector-demo --open
```

Đây là thao tác HTTP và thay đổi trạng thái trong application lab. Bảng không stream
desktop/terminal của VM, và không dựng lại màn hình tấn công hệ điều hành chưa chạy.

## Proxy cho repo khác / population cũ

Luồng proxy và sự kiện population cũ vẫn dùng được:

```bash
agent-office run -- python main.py
# hoặc: agent-office run -- npm start / uv run app.py / claude ...
```

Mở `http://127.0.0.1:7788` để xem. Agent nào gọi LLM sẽ tự xuất hiện ở Lõi LLM, rồi đi về bàn ngồi làm. Khi agent đang chờ model trả lời, trên đầu hiện 💭. Khi gọi tool, bong bóng hiện tên tool. Lúc agent giao việc cho agent khác, hạt dữ liệu bay từ người giao sang người nhận. Agent rảnh lâu sẽ ra sofa ngồi nghỉ.

## Cách hoạt động

```
repo multi-agent ──HTTP──▶ agent-office (proxy local) ──▶ API thật (OpenAI / Anthropic / tương thích)
                                  │
                                  └──SSE──▶ trình duyệt: văn phòng 3D
```

`agent-office run` bật một proxy local, rồi chạy lệnh của bạn với các biến môi trường sau:

| Biến | Giá trị |
|---|---|
| `OPENAI_BASE_URL`, `OPENAI_API_BASE` | `http://127.0.0.1:7788/openai` |
| `ANTHROPIC_BASE_URL` | `http://127.0.0.1:7788/anthropic` |

Request vẫn được chuyển lên API thật, kể cả streaming. Nếu trước đó bạn đã đặt `OPENAI_BASE_URL`, ví dụ trỏ tới OpenRouter, vLLM, LiteLLM hay Ollama (endpoint `/v1`), thì địa chỉ đó sẽ được dùng làm upstream. Proxy chuyển tiếp header xác thực; không có chức năng quản lý hay lưu key pool. Chế độ proxy phân tích prompt/response để suy ra hoạt động và có thể hiển thị đoạn nội dung đó; cơ chế này khác snapshot đã lọc của world.

Từ traffic đi qua, proxy suy ra:

| Thấy trong request/response | Hiển thị |
|---|---|
| Mỗi system prompt / `instructions` khác nhau | Một agent. Tên lấy từ "You are **X**…", nếu không có thì lấy từ vai trò, ví dụ "Note Summarizer" |
| Cùng system prompt chạy song song với các task khác nhau | Nhiều bản sao: `Worker`, `Worker #2`… |
| Prompt đầu tiên mới | Một task mới (📥) |
| `tool_calls` / `function_call` / `tool_use` | Bong bóng tool, robot gõ phím |
| Agent B bắt đầu task trong lúc agent A đang chờ kết quả tool | Giao việc A → B. Ưu tiên tool hoặc tham số có nhắc tên B, sau đó đến agent gọi tool gần nhất |
| `transfer_to_billing_agent` (kiểu OpenAI Agents SDK) | Đặt tên luôn cho agent nhận là "Billing Agent" |

Proxy hỗ trợ: OpenAI Chat Completions, OpenAI Responses API, Anthropic Messages, cả streaming lẫn non-streaming.

## Chạy demo (không cần API key)

Cần Node 18+, Python 3.9+ và `pip install openai anthropic`.

```bash
cd agent-office
node examples/run-demo.js --open
```

Lệnh này bật một LLM giả (`examples/mock-llm.js`) rồi chạy `examples/demo-team/team.py`. Đó là một repo Python bình thường, không biết gì về agent-office, gồm:

- **Mindy**: điều phối, giao việc qua tool `delegate`.
- **Hermes**: nghiên cứu, dùng chat completions có streaming.
- **Atlas**: phân tích dữ liệu, dùng Responses API.
- **Codex**: lập trình, dùng chat completions có streaming.
- **Scribe**: viết báo cáo, dùng Anthropic có streaming. Scribe gọi tool `summarize_notes`, tool này chạy 6 agent tóm tắt song song.

## Dùng với repo thật

```bash
# chạy trực tiếp từ thư mục package
node /đường/dẫn/agent-office/bin/agent-office.js run --open -- python main.py

# hoặc cài thành lệnh toàn cục
npm install -g /đường/dẫn/agent-office
agent-office run --open -- python main.py
```

Tuỳ chọn:

| Tuỳ chọn | Ý nghĩa |
|---|---|
| `--port 7788` | Cổng của viewer và proxy |
| `--open` | Tự mở trình duyệt |
| `--exit` | Tắt viewer khi lệnh con kết thúc. Mặc định viewer vẫn mở để bạn xem lại |
| `--openai-upstream URL` / `--anthropic-upstream URL` | Đổi nơi chuyển tiếp request |
| `--config file.json` | File đặt tên agent |

Nếu repo không chạy bằng một lệnh, ví dụ chạy trong notebook hoặc Docker, dùng `agent-office serve`. Lệnh này in ra các biến môi trường để bạn tự đặt cho repo.

### Đặt tên agent cho đẹp

Tạo file `agent-office.json` ở thư mục bạn chạy lệnh. Quy tắc đầu tiên khớp với system prompt sẽ được dùng:

```json
{
  "agents": [
    { "match": "orchestrator", "name": "Mindy", "role": "Điều phối", "color": "#ff7eb6" },
    { "regex": "research|search the web", "name": "Hermes", "role": "Nghiên cứu" }
  ]
}
```

Một cách khác là gửi header `X-Agent-Name: Hermes` trong request tới LLM. Nhiều SDK cho phép đặt `default_headers`.

### Gửi sự kiện thủ công (tuỳ chọn)

Với những bước không gọi LLM, bạn có thể tự bắn sự kiện vào `POST /ingest`:

```bash
curl -X POST $AGENT_OFFICE_URL/ingest -H 'content-type: application/json' -d '[
  {"type":"agent","id":"etl","name":"ETL Bot","role":"Data pipeline"},
  {"type":"status","id":"etl","state":"tool","text":"🔧 loading 10k rows"},
  {"type":"message","id":"etl","text":"Đã nạp xong dữ liệu"},
  {"type":"status","id":"etl","state":"idle"}
]'
```

`AGENT_OFFICE_URL` đã có sẵn trong môi trường của lệnh con. Các loại sự kiện: `agent`, `task`, `llm_start`, `tool`, `llm_end`, `llm_error`, `handoff`, `message`, `status`, `process`. World dùng thêm `world_snapshot` schema v1; server giữ snapshot mới nhất cho tối đa 16 world, replay khi tải lại trang. Xem `lib/snapshot.js` để biết các trường được chấp nhận. Khi có world, UI ưu tiên roster/counter của world; dùng viewer riêng để xem proxy cùng lúc.

## Giới hạn riêng của proxy

- Chỉ thấy được những gì đi qua HTTP tới LLM. Agent nói chuyện với nhau qua queue hoặc biến nội bộ thì chỉ được suy ra, không thấy trực tiếp.
- Repo hardcode URL API, hoặc SDK không đọc `*_BASE_URL`, sẽ đi thẳng ra ngoài mà không qua proxy. Trường hợp này cần thêm cấu hình hoặc chế độ HTTPS proxy, chưa làm.
- Proxy hỗ trợ định dạng API của OpenAI và Anthropic. Gemini native và Ollama `/api/chat` không qua proxy này; **SABER Gemini vẫn hiển thị bằng snapshot runtime**.
- Tên agent và giao việc là suy đoán. Dùng `agent-office.json` hoặc header `X-Agent-Name` để chính xác hơn.
- Proxy legacy dùng chỗ trống chung và khu đứng; không tự suy ra đội từ tên agent.
  Phân khu client/red/blue và chia trang theo đội dùng trường `team` trong snapshot world.

## Cấu trúc

```
bin/agent-office.js     CLI: run / serve / watch
lib/server.js           proxy + SSE + /ingest + /state
lib/analyzer.js         suy ra agent, task, tool, handoff từ traffic
lib/snapshot.js         schema snapshot đã lọc, giới hạn 200 actor
lib/watch.js            đọc file local hoặc snapshot container
viewer/index.html       văn phòng 3D đã build (three.js inline, chạy offline)
viewer-src/             mã nguồn viewer; world-state.js chứa selector có kiểm thử
viewer-src/inspector.js bảng chi tiết agent; trace-view.js chọn sự kiện theo bằng chứng
viewer-src/office-layout.js tọa độ ba khu, 72 bàn và phân trang theo từng đội
test/                   test protocol, watcher, trạng thái và browser smoke tùy chọn
examples/               mock LLM + repo demo multi-agent
```

Phần chạy (`bin`, `lib`, `viewer`) không có dependency nào. `three` và `esbuild` chỉ cần khi build lại viewer.

## Sửa code và kiểm thử

```powershell
cd agent-office
npm ci
npm run build:viewer
npm test
```

Commit cả `viewer-src` và `viewer/index.html` sau khi build. `npm test` không gọi API
LLM, không cần Docker hay trình duyệt. Test Docker dùng adapter giả; không thay thế
kiểm tra container thật. Test Python: `uv run pytest tests/world/test_office.py
tests/population/test_office.py tests/environments -q` từ root repo.

Smoke Chrome tùy chọn dùng `playwright-core` cài riêng: đặt `PLAYWRIGHT_MODULE` thành
đường dẫn package và `CHROME_PATH` thành đường dẫn Chrome, rồi từ root chạy:

```powershell
node agent-office/test/browser-smoke.cjs runs/world/office.json runs/office-browser-check
```

Đầu vào cần snapshot của world **đã dừng**. Test kiểm tra roster đó rồi dùng dữ liệu
thử để kiểm tra 200 agent, filter, quota, stale, resume và mobile; lưu ảnh cùng
`verification.json`. Dữ liệu thử không phải bằng chứng 200 agent đã chạy workload.
Nếu snapshot có trace và actor `red-impact` đã thực thi `register_job`, test kiểm thêm
bảng chi tiết, liên kết case/phản ứng, lọc thao tác riêng và cú bấm vào bàn 3D thật.
Một snapshot thử riêng kiểm việc hiển thị target như văn bản, không thực thi HTML.
Dùng demo 18 tick ở trên cho nhánh kiểm tra này.

Kiểm chứng lượt inspector ngày 2026-11-02: **121 test Python** (`tests/world`, `tests/environments`,
`tests/population/test_office.py`), **11 test JavaScript**, build viewer và Chrome smoke
đều qua; Ruff và mypy trên module Python thay đổi cũng qua. Demo scripted có 11 agent,
162 thao tác, 3 case và 5 phản ứng xác minh. Không gọi Gemini cho lượt kiểm tra UI này.
Artifact local: `runs/office-inspector-check/verification.json`, `red-agent-inspector.png`,
`mobile-inspector.png`; snapshot demo ở `runs/office-inspector-demo/office.json`.

Lượt phối lại ba khu: **12 test JavaScript**, build và Chrome smoke qua. Kiểm tra cả
36/72 slots, không trùng bàn, không lẫn khu, giữ chỗ khi lọc, phân trang đủ 200 agent,
camera, inspector và mobile. Roster 200 / ảnh 72 agent là dữ liệu UI thử nghiệm;
không phải 200 agents đã chạy workload. Artifact local:
`runs/office-team-zones-check/verification.json`, `actual-world.png`,
`synthetic-72-seats.png`, `blue-zone.png`, `mobile-team-zone.png`. Lượt này chỉ đổi
viewer, không chạy lại Gemini hay thay đổi runtime world.
