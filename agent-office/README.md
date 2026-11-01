# agent-office

Xem đội multi-agent của bạn làm việc trong một văn phòng 3D. Không cần sửa code của repo, chỉ cần chạy nó **qua** `agent-office`:

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

Request vẫn được chuyển nguyên vẹn lên API thật, kể cả streaming. Nếu trước đó bạn đã đặt `OPENAI_BASE_URL`, ví dụ trỏ tới OpenRouter, vLLM, LiteLLM hay Ollama (endpoint `/v1`), thì địa chỉ đó sẽ được dùng làm upstream. API key không bị đọc hay lưu lại.

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

`AGENT_OFFICE_URL` đã có sẵn trong môi trường của lệnh con. Các loại sự kiện: `agent`, `task`, `llm_start`, `tool`, `llm_end`, `llm_error`, `handoff`, `message`, `status`, `process`.

## Giới hạn

- Chỉ thấy được những gì đi qua HTTP tới LLM. Agent nói chuyện với nhau qua queue hoặc biến nội bộ thì chỉ được suy ra, không thấy trực tiếp.
- Repo hardcode URL API, hoặc SDK không đọc `*_BASE_URL`, sẽ đi thẳng ra ngoài mà không qua proxy. Trường hợp này cần thêm cấu hình hoặc chế độ HTTPS proxy, chưa làm.
- Mới hỗ trợ định dạng API của OpenAI và Anthropic. Gemini native và Ollama `/api/chat` chưa hỗ trợ. Nếu chúng có endpoint tương thích OpenAI thì vẫn dùng được qua endpoint đó.
- Tên agent và giao việc là suy đoán. Dùng `agent-office.json` hoặc header `X-Agent-Name` để chính xác hơn.
- Văn phòng có 20 bàn. Agent thứ 21 trở đi sẽ đứng ở khu trống.

## Cấu trúc

```
bin/agent-office.js     CLI: run / serve
lib/server.js           proxy + SSE + /ingest
lib/analyzer.js         suy ra agent, task, tool, handoff từ traffic
viewer/index.html       văn phòng 3D đã build (three.js inline, chạy offline)
viewer-src/             mã nguồn viewer. Build lại: npm i && npm run build:viewer
examples/               mock LLM + repo demo multi-agent
```

Phần chạy (`bin`, `lib`, `viewer`) không có dependency nào. `three` và `esbuild` chỉ cần khi build lại viewer.
