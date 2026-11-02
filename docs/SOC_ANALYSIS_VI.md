# Phân tích binary, memory và PCAP trong lab

Service `analysis` giữ mẫu theo SHA-256 và chạy hàng đợi phân tích riêng. Chỉ operator
nạp mẫu; blue DFIR/malware/network chọn engine bằng tên cố định. Client/red không có
credential hoặc network analysis. Mẫu được phân tích tĩnh, không chạy như chương trình.

Image có Volatility, YARA, tshark, Suricata và Java 21. Đặt Ghidra tương thích Java 21
tại `BUNDLE/tools/ghidra`, IDA Linux có license/IDAPython tại `BUNDLE/tools/ida`, symbols
tại `BUNDLE/tools/symbols`. Chúng được mount chỉ đọc. Không chép license vào source/Git.
Đường dẫn, timeout và giới hạn mẫu nằm trong `lab.json.analysis`. IDA Free không mặc nhiên
hỗ trợ mọi tính năng batch. Công cụ thiếu trả unavailable, không trả kết quả giả.

Trong `BUNDLE/source`, sau khi khởi động lab:

```powershell
uv run --no-sync saber lab analysis tools --bundle ..
uv run --no-sync saber lab analysis import --bundle .. --file PATH_TO_LAB_SAMPLE --kind binary
uv run --no-sync saber lab analysis samples --bundle ..
uv run --no-sync saber lab analysis run --bundle .. --sample SHA256 --engine builtin
uv run --no-sync saber lab analysis run --bundle .. --sample SHA256 --engine yara
uv run --no-sync saber lab analysis run --bundle .. --sample SHA256 --engine ghidra
uv run --no-sync saber lab analysis run --bundle .. --sample SHA256 --engine ida
uv run --no-sync saber lab analysis status --bundle .. --job-id JOB_UUID
```

Memory: import `--kind memory`, chọn `--engine volatility --profile windows-processes`,
`windows-network` hoặc `linux-processes`. Volatility dùng `--offline`; operator cung cấp
symbols phù hợp trước. PCAP: import `--kind pcap`, chọn `--engine tshark` hoặc `suricata`.
YARA/Suricata rules đi kèm chỉ phát hiện marker tổng hợp SABER, không phân loại malware.

Agent dùng `list_samples`, `tool_status`, `analyze_sample` (sample_id/engine/profile),
`analysis_status` (job_id). QUEUED/RUNNING là đang chờ. Restart giữa job ghi INDETERMINATE.
Receipt chứa PID, exit code, hash mẫu/report và evidence ID; hash mẫu được kiểm trước/sau.
Ghidra timeout không được coi là phân tích hoàn tất. Binary metadata mặc định có format,
entropy và chuỗi có giới hạn; Ghidra/IDA trả function metadata; Volatility trả record JSON.

API operator bind localhost `7792`; xem từ xa qua SSH tunnel. Report đầy đủ ở volume
`analysis`, đường dẫn `analysis/<job-id>/analysis.json`; Office có preview giới hạn.
Không có shell/path/script tùy ý trong args của agent. Output, timeout và disk budget áp dụng.

Đã kiểm thử YARA thật với marker/đối chứng và Volatility thật với ảnh không hợp lệ.
Positive acceptance cho memory image, Ghidra, IDA, tshark và Suricata cần máy đích có
công cụ/mẫu tương ứng. Test argv/schema không thay cho các lần chạy đó.

Tham chiếu: [Ghidra headless](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/RuntimeScripts/support/analyzeHeadlessREADME.md),
[IDA CLI](https://docs.hex-rays.com/9.0sp1/user-guide/configuration/command-line-switches),
[Volatility CLI](https://volatility3.readthedocs.io/en/latest/vol-cli.html),
[Suricata CLI](https://docs.suricata.io/en/latest/command-line-options.html).
