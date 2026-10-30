# IR · Chứng cứ số và phân tích artifact

Thu thập và xử lý chứng cứ số; phân tích artifact hệ điều hành (registry, scheduled task, service, prefetch, event
log, memory dump). Khách hàng phối hợp cung cấp memory dump và disk image theo yêu cầu. Đầu ra: bộ artifact đã xử
lý phục vụ dựng lại hành vi thực thi.

## Thu theo order of volatility (RFC 3227)

**Thứ tự thu — dễ mất nhất trước:**
`ram` → `network_connections` → `processes` → `disk_images` → `local_logs` → `archived_logs`
(RAM → kết nối đang mở → tiến trình → disk → log tại chỗ → log tập trung/lưu trữ).

**Cách bảo toàn từng loại**

| Loại | Phương pháp |
|---|---|
| RAM | `live_memory_acquisition` — thu khi máy còn chạy; không tắt máy, không cô lập trước |
| kết nối mạng | `snapshot_connections` — chụp bảng kết nối hiện hành |
| tiến trình | `capture_process_state` — chụp danh sách và trạng thái tiến trình |
| ổ đĩa | `forensic_disk_image` — ảnh bit-by-bit qua write-blocker, có hash |
| log tại chỗ | `copy_preserve_timestamps` — sao chép giữ nguyên timestamp |
| log tập trung | `export_from_central_store` — xuất từ kho log tập trung |

**Checklist bắt buộc cho mọi đợt thu:** **hash từng tệp** (SHA-256) · **biên bản thu giữ** · **chuỗi bàn giao**
(ai, khi nào, giao cho ai, vì sao). Thiếu một mục là gói bằng chứng không dùng được.

```json
{"collection_order": ["ram", "network_connections", "processes", "disk_images", "local_logs"],
 "preservation": {"ram": "live_memory_acquisition", "disk_images": "forensic_disk_image"},
 "checklist": ["hash từng tệp", "biên bản thu giữ", "chuỗi bàn giao"]}
```

## Thu dấu vết xâm nhập trên máy

Thu dấu vết trên toàn hệ thống, **kể cả dấu vết attacker cố xoá**: event 1102 (log bị xoá), EDR bị vô hiệu hoá, log
AV ghi nhận mã độc từng bị phát hiện nhưng xử lý không thành công.

1. Đưa bản sao về kho bằng chứng (vd `/workspace/evidence/`) **không làm đổi hash và timestamp của bản gốc** — đọc và
   sao chép; **không** di chuyển, **không** sửa bản gốc.
2. Thu đúng order of volatility, không chỉ thu đủ.
3. Chính hành vi chống điều tra là một dấu vết phải thu: sự kiện 1102, trạng thái service EDR, mục log AV "xử lý thất bại".

```json
{"collected": ["ram.lime", "netconn.txt", "Security.evtx", "av_history.log"],
 "collection_order": ["ram", "network_connections", "processes", "local_logs"],
 "hashes": {"Security.evtx": "…sha256…"}, "custody": [{"by": "…", "at": "…", "to": "…"}]}
```

## Khôi phục thông tin từ nguồn dữ liệu pháp y

Dựng lại hành vi **đã xảy ra trong quá khứ** từ log AV lịch sử, log hệ thống và artifact còn sót.

- **Phát hiện nhưng xử lý thất bại:** mục AV có hành động *quarantine/delete/clean failed*, *access denied*, *left
  alone*, *pending reboot* không hoàn tất; hoặc cùng hash bị phát hiện lặp lại trên cùng máy (nghĩa là chưa gỡ được).
  Ghi `{hash, host}`; phát hiện đã xử lý thành công thì không tính.
- **Sự kiện quá khứ** (thực thi, tạo tệp, persistence) từ log hệ thống + AV, sắp theo thời gian thật.
- **Khoảng log bị xoá hẳn:** ghi rõ là **`khong_du_du_kien`** (không đủ dữ kiện) cho khoảng đó — "không quan sát được"
  khác "không có gì xảy ra". Không lấp khoảng trống bằng suy đoán.

```json
{"failed_detections": [{"hash": "…", "host": "ws-07"}],
 "past_events": ["thực thi agentd.exe trên ws-07", "tạo task Updater"], "timeline": ["…"], "unknown_window": {"start": "…", "end": "…", "label": "khong_du_du_kien"}}
```

## Phân tích registry và cơ chế persistence

Rà **Run, RunOnce, Scheduled Tasks, Services, WMI Event Consumers**; trên Linux: **systemd, `.bashrc`,
`.bash_profile`**. Đầu ra: danh sách cơ chế duy trì truy cập bị cài cắm.

- Loại: `run_key` · `service` · `scheduled_task` · `wmi` · `startup` · `systemd`. Ghi đúng **vị trí** và đúng **loại**.
- **Độc** khi: trỏ tới binary ở thư mục người dùng/Temp/ProgramData lạ, không chữ ký, tên giả, tham số mã hoá, tạo gần
  thời điểm sự cố, hash khớp IOC. **Lành tính** điển hình: `Teams.lnk` trong Startup, service của phần mềm đã ký, task
  cập nhật của hãng.
- **WMI Event Consumer** (`ROOT\subscription:CommandLineEventConsumer=…` + filter + binding) là chỗ **hầu hết công cụ
  bỏ sót** — luôn kiểm namespace `ROOT\subscription`.
- Ghi kèm dấu vết chống điều tra liên quan (mục bị xoá, sửa thời gian).

```json
{"entries": [{"location": "ROOT\\subscription:CommandLineEventConsumer=updConsumer", "type": "wmi"},
             {"location": "/etc/systemd/system/synth-agent.service", "type": "systemd"}],
 "antiforensics": [{"kind": "timestomp", "location": "C:\\ProgramData\\upd\\upd.exe"}]}
```

## Phân tích bộ nhớ (fileless, process injection)

Phân tích memory dump để phát hiện **mã độc fileless** và **process injection** — mã chạy thẳng trong bộ nhớ để né
phát hiện dựa trên tệp. Công cụ: Volatility (`malfind`, `ldrmodules`, `hollowfind`, `netscan`…).

**Dấu hiệu inject**
- Vùng nhớ **private, không gắn tệp image**, quyền **RWX/RX**, chứa **PE header (`MZ`)** hoặc shellcode.
- Thread bắt đầu tại địa chỉ **không thuộc module nào** đã nạp.
- Module có trong bộ nhớ nhưng **bị gỡ khỏi danh sách PEB** (DLL unlinked) — reflective loading.
- Image base/nội dung khác bản trên đĩa ⇒ **process hollowing**.

**Kỹ thuật:** DLL injection (CreateRemoteThread + LoadLibrary) · PE injection (T1055.002) · thread execution
hijacking (T1055.003) · APC injection (T1055.004) · process hollowing (T1055.012) · reflective DLL loading.

**Đừng nhầm:** tiến trình hợp lệ **có vùng RWX** vì JIT (.NET, Java, trình duyệt). RWX một mình không đủ — cần thêm
PE header/shellcode + không gắn image + thread lạ; kiểm tiến trình có nạp runtime JIT (`clr.dll`, `jvm.dll`) không.

**IOC chỉ có trong RAM:** chuỗi C2 đã giải mã, URL/IP trong vùng inject, khoá/mutex, lệnh PowerShell đã giải mã.

```json
{"injected": [{"pid": 4120, "module": "explorer.exe"}], "technique": {"4120": "process hollowing"},
 "ioc": {"url": ["http://198.51.100.4/gate.php"]}}
```

## Sai lầm thường gặp

- Cô lập/tắt máy trước khi thu RAM; thu log trước RAM.
- "Thu thập" bằng cách di chuyển bản gốc.
- Lấp khoảng log bị xoá bằng suy đoán.
- Bỏ sót WMI Event Consumer.
- Coi mọi tiến trình JIT có RWX là bị inject.

Nguồn nghiệp vụ: NICE T1324, T1370, T1607, T0397, T1253 (catalog SABER).
