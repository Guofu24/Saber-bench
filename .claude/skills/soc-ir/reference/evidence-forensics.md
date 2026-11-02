# IR · Chứng cứ số và phân tích artifact

Thu thập và xử lý chứng cứ số; phân tích artifact hệ điều hành (registry, scheduled task, service, prefetch, event
log, memory dump). Khách hàng phối hợp cung cấp memory dump và disk image theo yêu cầu. Đầu ra: bộ artifact đã xử
lý phục vụ dựng lại hành vi thực thi.

## Thu theo SOP và độ dễ mất của chứng cứ

**Thứ tự trong SOP của các case tương ứng:**
`ram` → `network_connections` → `processes` → `disk_images` → `local_logs` → `archived_logs`
(RAM → kết nối đang mở → tiến trình → disk → log tại chỗ → log tập trung/lưu trữ).

Chỉ áp dụng thứ tự này khi SOP/contract của case yêu cầu; không phải quy tắc chung cho mọi máy.
Case benchmark yêu cầu RAM trước cô lập vẫn giữ điều kiện đó. Trong sự cố thật, xét tác hại đang diễn ra,
retention, độ ổn định và đường thu từ xa; IR có thể cần cô lập trước. Ghi quyết định và chứng cứ bị mất.
[RFC 3227 §2](https://www.rfc-editor.org/rfc/rfc3227.html#section-2) nêu nguyên tắc ưu tiên dữ liệu dễ mất và
ghi nhận ảnh hưởng của việc thu. Live acquisition có thể đổi trạng thái; không hứa "không dấu vết".

**Cách bảo toàn từng loại**

| Loại | Phương pháp |
|---|---|
| RAM | `live_memory_acquisition` — thu khi máy còn chạy; xét ảnh hưởng cô lập tới đường thu, tránh reboot không cần thiết |
| kết nối mạng | `snapshot_connections` — chụp bảng kết nối hiện hành |
| tiến trình | `capture_process_state` — chụp danh sách và trạng thái tiến trình |
| ổ đĩa | `forensic_disk_image` — ảnh bit-by-bit qua write-blocker, có hash |
| log tại chỗ | `copy_preserve_timestamps` — sao chép giữ nguyên timestamp |
| log tập trung | `export_from_central_store` — xuất từ kho log tập trung |

**Checklist bắt buộc cho mọi đợt thu:** **hash từng tệp** (SHA-256) · **biên bản thu giữ** · **chuỗi bàn giao**
(ai, khi nào, giao cho ai, vì sao). Thiếu mục: giữ dữ liệu, ghi hạn chế và yêu cầu bổ sung; không tự loại bỏ
mọi giá trị điều tra hay phán quyết giá trị pháp lý. Case có checklist bắt buộc vẫn báo chưa đạt.

```json
{"collection_order": ["ram", "network_connections", "processes", "disk_images", "local_logs"],
 "preservation": {"ram": "live_memory_acquisition", "disk_images": "forensic_disk_image"},
 "checklist": ["hash từng tệp", "biên bản thu giữ", "chuỗi bàn giao"]}
```

## Thu dấu vết xâm nhập trên máy

Thu dấu vết trên toàn hệ thống, **kể cả dấu vết attacker cố xoá**: event 1102 (log bị xoá), EDR bị vô hiệu hoá, log
AV ghi nhận mã độc từng bị phát hiện nhưng xử lý không thành công.

1. Đưa bản sao về kho bằng chứng (vd `/workspace/evidence/`) **không làm đổi hash và timestamp của bản gốc** — đọc và
   sao chép; **không** di chuyển, **không** sửa bản gốc. Dùng image/read-only mount/write-blocker phù hợp;
   nếu không bảo đảm ràng buộc bất biến của case thì báo thiếu công cụ, không tự nới yêu cầu.
2. Thu theo thứ tự phù hợp rủi ro; lưu lý do nếu khác SOP được giao.
3. Chính hành vi chống điều tra là một dấu vết phải thu: sự kiện 1102, trạng thái service EDR, mục log AV "xử lý thất bại".

```json
{"collected": ["ram.lime", "netconn.txt", "Security.evtx", "av_history.log"],
 "collection_order": ["ram", "network_connections", "processes", "local_logs"],
 "hashes": {"Security.evtx": "…sha256…"}, "custody": [{"by": "…", "at": "…", "to": "…"}]}
```

## Khôi phục thông tin từ nguồn dữ liệu pháp y

Dựng lại hành vi **đã xảy ra trong quá khứ** từ log AV lịch sử, log hệ thống và artifact còn sót.

- **Phát hiện nhưng xử lý thất bại:** mục AV có hành động *quarantine/delete/clean failed*, *access denied*, *left
  alone*, *pending reboot* chưa có kết quả hoàn tất. Phát hiện lặp cùng hash có thể do tái nhiễm hoặc quét kho cách ly;
  đối chiếu action ID, path, trạng thái kết thúc và thời gian. Ghi `{hash, host}` khi có bằng chứng xử lý thất bại;
  trạng thái thành công phải kiểm theo đúng lần xử lý, không suy máy đã sạch hoàn toàn.
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
- **Đầu mối:** binary trong Temp/ProgramData lạ, không chữ ký, tên giả, tham số mã hoá, thời điểm tạo bất thường.
  Kết luận bằng target/command, hash, creator và hành vi. `Teams.lnk`, service đã ký hoặc task cập nhật vẫn cần
  kiểm baseline; tên và chữ ký không tự chứng minh hợp lệ.
- **WMI Event Consumer** (`ROOT\subscription:CommandLineEventConsumer=…` + filter + binding): kiểm namespace
  `ROOT\subscription` khi điều tra persistence; đối chiếu baseline, không mặc định là độc hại.
- Ghi kèm dấu vết chống điều tra liên quan (mục bị xoá, sửa thời gian).

```json
{"entries": [{"location": "ROOT\\subscription:CommandLineEventConsumer=updConsumer", "type": "wmi"},
             {"location": "/etc/systemd/system/synth-agent.service", "type": "systemd"}],
 "antiforensics": [{"kind": "timestomp", "location": "C:\\ProgramData\\upd\\upd.exe"}]}
```

## Phân tích bộ nhớ (fileless, process injection)

Phân tích memory dump để phát hiện **mã độc fileless** và **process injection** — mã chạy thẳng trong bộ nhớ để né
phát hiện dựa trên tệp. Chỉ dùng plugin Volatility có trong môi trường và tương thích phiên bản/symbols của ảnh;
ghi phiên bản, lệnh và lỗi. Các tên như `malfind`, `ldrmodules`, `hollowfind`, `netscan` không bảo đảm đã được cài.

**Dấu hiệu inject**
- Vùng nhớ **private, không gắn tệp image**, quyền **RWX/RX**, chứa **PE header (`MZ`)** hoặc shellcode.
- Thread bắt đầu tại địa chỉ **không thuộc module nào** đã nạp.
- Module không khớp danh sách PEB: điều tra unlink/loading, không tự quy thành reflective loading.
- Image base/nội dung khác bản trên đĩa: kiểm relocation, hotpatch và tính tương thích ảnh trước khi nghi hollowing.
  Kết hợp vùng nhớ, entry point/thread, backing file và dấu vết tạo tiến trình; một khác biệt chưa đủ kết luận.

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

- Áp một thứ tự thu RAM/cô lập cho mọi sự cố; bỏ qua yêu cầu riêng của case hoặc tác hại đang diễn ra.
- "Thu thập" bằng cách di chuyển bản gốc.
- Lấp khoảng log bị xoá bằng suy đoán.
- Bỏ sót WMI Event Consumer.
- Coi mọi tiến trình JIT có RWX là bị inject.

Nguồn nghiệp vụ: NICE T1324, T1370, T1607, T0397, T1253 (catalog SABER).
