# HUNT · Ánh xạ ATT&CK và chân dung xâm nhập

## Nhận diện chiến thuật và kỹ thuật (MITRE ATT&CK)

Toàn bộ rule và use-case của SOC được mapping theo MITRE ATT&CK; bạn nhận diện TTP dựa trên tri thức TI (IOC, TTP,
kho dữ liệu nhóm APT). Đầu ra: TTP được nhận diện và ánh xạ vào ATT&CK.

**Cách ánh xạ một hành vi**
1. Đọc **ý đồ** của lệnh/hành vi, không đọc tên tool: cùng `powershell` có thể là Execution, Discovery hay Defense
   Evasion tuỳ tham số.
2. Chọn **sub-technique** khi bằng chứng đủ cụ thể; chỉ dùng technique cha khi không xác định được biến thể.
3. Không chắc technique thì ít nhất phải đúng **tactic**.

**Ví dụ chuẩn**

| Dòng lệnh / hành vi | Technique | Tactic |
|---|---|---|
| `schtasks /create /tn Updater /tr app.exe /sc hourly` | T1053.005 Scheduled Task | persistence |
| `reg add HKCU\…\Run /v Updater /d app.exe` | T1547.001 Run Keys | persistence |
| `net user labadmin /add` | T1136.001 Local Account | persistence |
| `powershell -enc …` | T1059.001 PowerShell | execution |
| `cmd /c whoami /all` | T1033 System Owner/User Discovery | discovery |
| `net group "Domain Admins" /domain` | T1069.002 Domain Groups | discovery |
| `wmic process call create app.exe` | T1047 WMI | execution |
| `vssadmin delete shadows /all` | T1490 Inhibit System Recovery | impact |
| `rundll32 comsvcs.dll MiniDump …` | T1003.001 LSASS Memory | credential-access |
| `bitsadmin /transfer job http://… out.bin` | T1197 BITS Jobs | defense-evasion |

**Chuỗi nhiều hành vi:** ánh xạ **từng** hành vi, kể cả hành vi "nhỏ" (discovery).

**Bắt buộc dẫn chứng từng technique.** Liệt kê 30 technique cho chắc là vô nghĩa: chỉ ghi technique có bản ghi
thật chứng minh, kèm ID bản ghi đó.

```json
{"techniques": [{"technique": "T1059.001", "tactic": "execution", "evidence": ["PROC-…"]},
                {"technique": "T1053.005", "tactic": "persistence", "evidence": ["TASK-…"]}]}
```

## Chân dung cuộc xâm nhập vào một nạn nhân

Mô tả **mức độ kiểm soát của attacker trong hệ thống khách hàng**: điểm xâm nhập, leo thang đặc quyền, **di chuyển
ngang**, cơ chế **persistence**, truy cập dữ liệu nhạy cảm, exfiltration.

**Nhận diện cạnh di chuyển ngang**
- Logon type **3** (network: SMB/PsExec/WMI) hoặc **10** (RDP), event 4624/4648, từ máy **không phải jump host/PAM**,
  ngoài lịch quản trị, bằng tài khoản vừa bị chiếm hoặc không thường đăng nhập vào máy đích.
- Đi kèm thực thi từ xa trên máy đích (service mới 7045, `psexesvc`, `wmiprvse` sinh tiến trình lạ).
- Cạnh có hướng `src → dst`; host dùng tên ngắn; account bỏ domain. Không đưa phiên quản trị hợp lệ.

**Persistence:** `{kind, location}` — kind: run_key, service, scheduled_task, wmi, startup, systemd, cron…; location
là đường dẫn/khoá registry.

**Chân dung trọn vẹn** trên một case đã khép nhưng chưa có kết luận: tự dựng lại từ hiện vật, không suy từ tên case.

```json
{"vector": "khai thác dịch vụ phơi ra ngoài",
 "lateral_edges": [{"src": "web-01", "dst": "srv-db-01", "account": "svc_web"}],
 "persistence": [{"kind": "service", "location": "HKLM\\SYSTEM\\CurrentControlSet\\Services\\updsvc"}],
 "attck": ["T1190", "T1021.002", "T1543.003"], "evidence": ["…"]}
```

## Sai lầm thường gặp

- Ánh xạ theo tên tool thay vì ý đồ của lệnh; bỏ qua sub-technique.
- Liệt kê technique không có bằng chứng.
- Coi mọi logon type 3 là di chuyển ngang (jump host, SCCM/Ansible là hợp lệ).
- Đảo chiều cạnh `src`/`dst`.

Nguồn nghiệp vụ: NICE T0845, T1053 (catalog SABER).
