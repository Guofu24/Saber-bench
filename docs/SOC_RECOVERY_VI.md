# Sao lưu, chuyển máy và khôi phục SOC lab

Backup này lưu toàn bộ named volumes: raw log/archive, index OpenSearch, queue,
workspace, browser artifacts, phiên bản skill, mẫu phân tích và SOAR receipts.
Nó cũng lưu **credential dịch vụ** trong archive riêng; lưu backup trên vùng lưu trữ
riêng có kiểm soát truy cập/mã hóa. Không xuất Gemini key pool hoặc cấu hình bật API.
Giữ một bản nguyên vẹn của bundle đã render; restore yêu cầu đúng manifest/code/spec.
Các bộ cài/symbols/license tùy chọn trong `tools/` cần copy hoặc cài riêng; chúng không
nằm trong named-volume backup. Giữ Gemini key pool riêng ngoài `.secrets/`.

## Linux/container

```powershell
saber lab backup create --bundle runs/my-lab --out D:/PrivateBackups/soc-001 --on-target
saber lab backup verify --bundle runs/my-lab --backup D:/PrivateBackups/soc-001
```

Lệnh create dừng controller rồi dừng dịch vụ, kiểm quyền sở hữu volume và không còn
container dùng volume đang chạy. Helper chạy không có network, archive theo luồng,
ghi checksum và giữ UID/GID/mode khi chạy trên Linux. Dịch vụ **được để dừng** sau
backup. Dùng `lab up --bundle ... --on-target` để chạy lại; thêm các cờ Gemini nếu cần.
Không chạy đồng thời lệnh start/restore/backup khác trên cùng deployment.

Trên máy mới, copy bundle nguyên gốc (không `.secrets`, không receipt runtime),
copy backup, cài Python/uv/Docker như runbook rồi chạy:

```powershell
saber lab backup restore --bundle runs/my-lab --backup D:/PrivateBackups/soc-001 --on-target
saber lab up --bundle runs/my-lab --on-target
saber lab analysis self-test --bundle runs/my-lab
saber lab verify --bundle runs/my-lab
```

Không chạy `lab credentials` trước restore. Restore kiểm checksum, từ chối link,
path traversal và target đã có volume/credential; không xóa hoặc ghi đè lab đang có.
Nếu lỗi giữa chừng, dữ liệu khôi phục dở được giữ để điều tra, không tự chạy dịch vụ.
Chọn target sạch sau khi xử lý lỗi. Job có kết quả không rõ vẫn giữ trạng thái cũ,
không biến thành thành công và không tự chạy lại. Backup không hoàn lại quota Gemini.

## Windows/AD: giữ cả domain cùng một mốc

1. `saber lab stop --bundle ...`; chờ job hiện tại hoàn tất hoặc ghi nhận pending.
2. Dừng process `Relay-Lab.ps1` đang chạy. Giữ relay dừng suốt quá trình backup.
3. Trên Hyper-V host, PowerShell Administrator:

```powershell
./windows/Backup-Lab.ps1 -Bundle . -Out D:/PrivateBackups/soc-guests-001 -OnTarget
```

Script xác minh VM thuộc bundle, shutdown toàn bộ, Export-VM và hash tất cả file.
Không force power-off. Giữ guest tắt; chia sẻ/copy nguyên export tới host chạy CLI:

```powershell
saber lab backup create --bundle runs/my-lab --out D:/PrivateBackups/soc-001 --windows-backup D:/PrivateBackups/soc-guests-001 --on-target
saber lab backup verify --bundle runs/my-lab --backup D:/PrivateBackups/soc-001 --windows-backup D:/PrivateBackups/soc-guests-001
```

Restore cả Docker với `--windows-backup` và toàn bộ guest trên host Hyper-V sạch:

```powershell
./windows/Restore-Lab.ps1 -Bundle . -Backup D:/PrivateBackups/soc-guests-001 -VmRoot D:/SaberRestored -OnTarget
```

Script kiểm hash/roster, không đè VM đang tồn tại, dùng Compare-VM trước import,
sửa ánh xạ switch sang private switch của lab. Guest vẫn tắt sau import.
Sau khi cả hai phần đã restore, bật DC trước, rồi các member, chạy lại relay và SOC.
Relay có thể đọc lại log cũ; ID Windows event ổn định nên collector deduplicate.
Các tài khoản/mật khẩu Windows và giấy phép vẫn do operator quản lý.

`verification.receipt.json` mới sau restore phải đạt; checksum backup chỉ chứng minh
toàn vẹn archive. Test local đã khôi phục SQLite/outbox/artifact thật; import Hyper-V,
khôi phục volume Docker/OpenSearch và AD cần nghiệm thu trên host đủ tài nguyên.

Tham chiếu: [Export-VM](https://learn.microsoft.com/en-us/powershell/module/hyper-v/export-vm),
[Import-VM](https://learn.microsoft.com/en-us/powershell/module/hyper-v/import-vm),
[Compare-VM](https://learn.microsoft.com/en-us/powershell/module/hyper-v/compare-vm).
