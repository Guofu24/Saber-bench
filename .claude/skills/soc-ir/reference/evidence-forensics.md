# IR · Chứng cứ số và phân tích artifact — T1324 · T1370 · T1607 · T0397 · T1253

Thu và xử lý chứng cứ số: artifact hệ điều hành (registry, scheduled task, service, prefetch, event log,
memory dump); khách hàng phối hợp cung cấp memory dump và disk image theo yêu cầu. Đầu ra: bộ artifact đã
xử lý phục vụ dựng lại hành vi thực thi.

---

## T1324 — Xử lý chứng cứ số (order of volatility)

| Subtask | Mode | Đầu vào | Phải nộp | Chấm |
|---|---|---|---|---|
| **T1324.001** | file | HV-36 (8 loại bằng chứng) | `collection_order[]` | Kendall τ |
| **T1324.002** | file | HV-20, HV-36 | `collection_order[]`, `preservation{}` | 0.6 (τ × recall) + 0.4 accuracy |
| **T1324.003** | file | HV-16 18 20 26 31 36 38 | `collection_order[]`, `checklist[]` | 0.6 + 0.4 recall, **cap 0.6 nếu thiếu 1 mục checklist** |

**Order of volatility (RFC 3227) — thứ tự chuẩn của gold pilot**
`ram` → `network_connections` → `processes` → `disk_images` → `local_logs` → `archived_logs`
(nguồn: RAM → kết nối đang mở → tiến trình → disk → log tập trung). Liệt kê đủ mọi loại có trong đề, dễ mất
nhất trước, đúng token loại của input.

**Cách bảo toàn từng loại (.002) — token của gold pilot (chờ adjudication)**

| Loại | Token phương pháp | Ý nghĩa |
|---|---|---|
| `ram` | `live_memory_acquisition` | thu RAM khi máy còn chạy (không tắt máy, không cô lập trước) |
| `network_connections` | `snapshot_connections` | chụp bảng kết nối hiện hành |
| `processes` | `capture_process_state` | chụp danh sách/trạng thái tiến trình |
| `disk_images` | `forensic_disk_image` | ảnh đĩa bit-by-bit qua write-blocker, hash |
| `local_logs` | `copy_preserve_timestamps` | sao chép giữ nguyên timestamp |
| `archived_logs` | `export_from_central_store` | xuất từ kho log tập trung |

Input chỉ cho **từ vựng** phương pháp (`method_vocabulary`), không cho ánh xạ — phải tự ánh xạ.

**Checklist bắt buộc (.003)** — thiếu một mục ⇒ trần 0.6: **hash từng tệp** (SHA-256) · **biên bản thu
giữ** · **chuỗi bàn giao** (chain of custody: ai, khi nào, chuyển cho ai, mục đích). Dùng đúng nhãn mục
như đề.

---

## T1370 — Thu thập dấu vết xâm nhập (mode vm)

Thu dấu vết trên toàn hệ thống, **kể cả dấu vết attacker cố xoá**: log 1102 bị xoá, EDR bị vô hiệu hoá, log
AV ghi nhận mã độc từng bị phát hiện nhưng xử lý không thành công.

| Subtask | Mode | Đầu vào | Chấm |
|---|---|---|---|
| **T1370.001** | vm | HV-36 (M dấu vết) | recall `collected[]` × **[bằng chứng nguyên vẹn]** (hash + mtime) |
| **T1370.002** | vm | HV-14, HV-36 | recall × gate — attacker đã xoá log 1102, tắt EDR, AV xử lý thất bại |
| **T1370.003** | vm | HV-04 15 16 18 20 36 37 38 | 0.5 recall + 0.3 nguyên vẹn + 0.2 `collection_order[]` |

- Đích thu: `/workspace/evidence/`, **không làm đổi hash và timestamp gốc**.
- Mô hình hành động offline không có `copy`: khai báo `{"op": "read", "path": ...}` cho từng nguồn và liệt
  kê dấu vết trong `observations.collected` (đúng khoá theo `scored_fields`). **Không `move`/`modify`
  bản gốc** — gate `evidence_intact` so hash + mtime.
- .002: chính hành vi chống điều tra là dấu vết phải thu (xem `soc-hunt/reference/intrusion-analysis.md`
  T2013): sự kiện 1102, trạng thái service EDR, mục log AV "xử lý thất bại".
- .003: thu đúng **order of volatility**, không chỉ thu đủ.

---

## T1607 — Khôi phục thông tin từ nguồn dữ liệu pháp y

Khôi phục từ log AV lịch sử, log hệ thống và artifact còn sót trên endpoint để **dựng lại hành vi đã xảy
ra trong quá khứ**.

| Subtask | Mode | Đầu vào | Phải nộp | Chấm |
|---|---|---|---|---|
| **T1607.001** | file | HV-14 log AV lịch sử | `failed_detections[]` `{hash, host}` | set_delta |
| **T1607.002** | file | HV-02, HV-14 | `past_events[]`, `timeline[]` | 0.5 recall + 0.5 thứ tự+recall |
| **T1607.003** | soc (SIEM, EDR) | HV-02 04 14 15 16 18 26 27 38 | + `unknown_window` | Σ × **[nhận ra khoảng không quan sát được]** |

- **.001 — phát hiện nhưng xử lý thất bại:** mục AV có hành động *quarantine/delete/clean failed*, *access
  denied*, *left alone*, *pending reboot* không hoàn tất, hoặc cùng hash bị phát hiện lặp lại trên cùng máy
  (nghĩa là chưa bị gỡ). Phần tử `{hash, host}`; phát hiện đã xử lý thành công **không** đưa vào.
- **.002:** sự kiện quá khứ (thực thi, tạo file, persistence) từ log hệ thống + AV, sắp theo thời gian thật.
- **.003 — bẫy cố ý:** một khoảng log bị **xoá hẳn**; nhãn cho khoảng đó là **`khong_du_du_kien`** — đo khả
  năng phân biệt "không có" với "không quan sát được". Đối chiếu HV-04 (sức khoẻ log source) và nhịp ghi
  log để chỉ ra khoảng trống; không điền sự kiện tưởng tượng vào đó.

---

## T0397 — Phân tích Windows registry (và tương đương Linux)

Rà soát cơ chế persistence: khoá **Run, RunOnce**, **Scheduled Tasks**, **Services**, **WMI Event
Consumers**; Linux: **systemd**, `.bashrc`, `.bash_profile`. Đầu ra: danh sách cơ chế duy trì truy cập bị
cài cắm.

| Subtask | Mode | Đầu vào | Phải nộp | Chấm |
|---|---|---|---|---|
| **T0397.001** | file | HV-16 (K mục, M độc) | `malicious_entries[]` (path) | set_delta |
| **T0397.002** | file | HV-16, HV-18 | `entries[]` **`{location, type}`** | F1, **đúng vị trí sai loại = 0.5 phần tử** |
| **T0397.003** | vm | HV-15 16 18 20 26 (K = 40, M = 8) | `entries[]`, `antiforensics[]` | 0.8 + 0.2 |

- `type` ∈ `run_key` · `service` · `scheduled_task` · `wmi` · `startup` · `systemd` (exemplar
  T0397.002 dùng khoá **`location` + `type`** — theo `output_schema`, không phải `kind`).
- **Độc** khi: trỏ tới binary ở thư mục người dùng/Temp/ProgramData lạ, không chữ ký, tên giả, tham số
  encode, tạo gần thời điểm sự cố, hash khớp IOC (HV-18). **Lành tính** điển hình: `Teams.lnk` trong
  Startup, service của phần mềm đã ký, task cập nhật hãng.
- **WMI Event Consumer** (`ROOT\subscription:CommandLineEventConsumer=…` + filter + binding) — chỗ hầu hết
  công cụ **bỏ sót**; .003 cấy đúng một mục này. Luôn kiểm namespace `ROOT\subscription`.
- `antiforensics[]` (.003) `{kind, location}`: mục bị xoá/sửa thời gian, log bị xoá liên quan.

---

## T1253 — Phân tích động trên ổ/bộ nhớ (memory forensics)

Phân tích memory dump để phát hiện **fileless malware** và **process injection** — mã độc chạy thẳng
trong bộ nhớ để né phát hiện dựa trên file. Đầu ra: dấu hiệu xâm nhập chỉ tồn tại trong bộ nhớ.

| Subtask | Mode | Đầu vào | Phải nộp | Chấm |
|---|---|---|---|---|
| **T1253.001** | file | HV-20 vùng nhớ của N tiến trình (M bị inject) | `injected[]` (pid) | set_delta |
| **T1253.002** | file | HV-15, HV-20 | `injected[]` `{pid, module}`, `technique{}` | 0.7 / 0.3 |
| **T1253.003** | file | HV-15 16 17 18 20 36 (ảnh bộ nhớ thật) | `injected[]` `{pid, module}`, `ioc{}` | 0.5 / 0.5 |

**Dấu hiệu inject** (kiểu Volatility `malfind`/`ldrmodules`/`hollowfind`)
- Vùng nhớ **private, không gắn file image**, quyền **RWX/RX**, chứa **PE header (`MZ`)** hoặc shellcode.
- Thread bắt đầu tại địa chỉ **không thuộc module nào** đã nạp.
- Module có trong bộ nhớ nhưng **bị gỡ khỏi danh sách PEB** (DLL unlinked) — reflective DLL.
- Image base / nội dung khác bản trên đĩa ⇒ **process hollowing**.

**Kỹ thuật (`technique{}`, dùng đúng nhãn của đề):** DLL injection (CreateRemoteThread + LoadLibrary),
PE injection (T1055.002), thread execution hijacking (T1055.003), APC injection (T1055.004), process
hollowing (T1055.012), reflective DLL loading.

**Mẫu âm bắt buộc (.002):** tiến trình hợp lệ **có vùng RWX** — JIT của .NET/Java, trình duyệt (V8). RWX
một mình **không** đủ; cần thêm PE header/shellcode + không gắn image + thread lạ, và đối chiếu tiến trình
có nạp runtime JIT (`clr.dll`, `jvm.dll`) không.

**.003 — IOC chỉ tồn tại trong RAM:** chuỗi C2 giải mã, URL/IP trong vùng inject, khoá/mutex, lệnh
PowerShell đã giải mã. Định dạng IOC theo `soc-cnt/reference/coverage-intel.md`.

## Bẫy hay gặp

- Cô lập/tắt máy trước khi thu RAM; thu log trước RAM.
- "Thu thập" bằng `move` ⇒ hỏng tính nguyên vẹn.
- Bỏ qua khoảng log bị xoá hoặc lấp nó bằng suy đoán.
- Bỏ sót WMI Event Consumer; dùng khoá `kind` khi schema đòi `type`.
- Báo mọi tiến trình JIT có RWX là bị inject.
