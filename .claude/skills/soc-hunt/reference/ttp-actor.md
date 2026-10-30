# HUNT · Chiến thuật, kỹ thuật và chân dung xâm nhập — T0845 (ATT&CK) · T1053 (mô tả xâm nhập nhằm vào nạn nhân)

---

## T0845 — Nhận diện chiến thuật và phương thức của mối đe doạ

Nhận diện chiến thuật/kỹ thuật dựa trên tri thức Viettel TI (hàng triệu IOC và TTP, kho dữ liệu APT).
Toàn bộ rule và use-case được **mapping theo MITRE ATT&CK**. Đầu ra: TTPs ánh xạ vào khung ATT&CK.

| Subtask | Mode | Đầu vào | Phải nộp | Chấm |
|---|---|---|---|---|
| **T0845.001** | file | HV-15 (1 dòng lệnh) | `technique` | **1.0 đúng technique · 0.5 đúng tactic · 0 sai cả hai** |
| **T0845.002** | file | HV-15, HV-16 (chuỗi 10 hành vi) | `techniques[]` | macro-average (1.0 technique / 0.5 tactic mỗi hành vi) |
| **T0845.003** | soc (EDR, SIEM) | HV-02 04 15 16 17 26 33 35 38 | `techniques[]`, `citations[]` | macro-average; **technique không grep được bằng chứng bị loại khỏi tử số** |

**Cách ánh xạ một hành vi**
1. Đọc **ý đồ** của lệnh/hành vi, không đọc tên tool: cùng `powershell` có thể là Execution, Discovery
   hay Defense Evasion tuỳ tham số.
2. Chọn **sub-technique** khi bằng chứng đủ cụ thể (scorer phân biệt sub-technique); chỉ dùng technique
   cha khi không xác định được biến thể.
3. Nếu không chắc technique, ít nhất chọn technique **đúng tactic** — vẫn được 0.5. `tactic_catalog`
   trong input của exemplar cho biết tactic của từng technique.

**Ví dụ chuẩn (exemplar T0845.001)**

| Dòng lệnh | Technique | Tactic |
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

**.002 — chuỗi 10 hành vi:** ánh xạ **từng** hành vi; điểm trung bình theo hành vi ⇒ đừng bỏ hành vi
nào, kể cả hành vi "nhỏ" (discovery).

**.003 — bắt buộc dẫn chứng từng technique:** nếu không, model liệt kê 30 technique là "ăn hết recall".
Chỉ liệt kê technique có bản ghi thật chứng minh, và đưa evidence ID của **mỗi** technique vào
`citations[]`. Technique không có bằng chứng bị loại khỏi tử số — liệt kê thừa không giúp gì, trích ID
bịa còn làm mất cả gate.

---

## T1053 — Nhận diện và mô tả hoạt động xâm nhập nhằm vào một nạn nhân

Mô tả **chân dung cuộc xâm nhập vào chính khách hàng**: điểm xâm nhập, leo thang đặc quyền, **lateral
movement**, cơ chế **persistence**, truy cập dữ liệu nhạy cảm, exfiltration. Đầu ra: chân dung đầy đủ về
mức độ kiểm soát của attacker trong hệ thống.

| Subtask | Mode | Đầu vào | Phải nộp | Chấm |
|---|---|---|---|---|
| **T1053.001** | file | HV-26 (N phiên, M là di chuyển ngang) | `lateral_edges[]` `{src, dst}` | set_delta |
| **T1053.002** | file | HV-15, HV-16, HV-26 | `lateral_edges[]` `{src, dst, account}`, `persistence[]` `{kind, location}` | 0.5 / 0.5 |
| **T1053.003** | soc (SIEM, EDR) | HV-02 04 15 16 18 22 26 32 33 (case đã khép, cắt sạch kết luận) | `vector`, `lateral_edges[]`, `persistence[]`, `attck[]` | 0.3 / 0.3 / 0.2 / 0.2 |

**Nhận diện cạnh di chuyển ngang (HV-26)**
- Logon type **3** (network: SMB/PsExec/WMI) hoặc **10** (RemoteInteractive/RDP), event 4624/4648, từ
  máy **không phải jump host/PAM**, ngoài lịch quản trị, bằng tài khoản vừa bị chiếm hoặc tài khoản
  không thường đăng nhập vào máy đích.
- Đi kèm thực thi từ xa trên máy đích (service mới 7045, `psexesvc`, `wmiprvse` sinh tiến trình lạ).
- Cạnh có hướng `src → dst`; host chuẩn hoá tên ngắn; account bỏ domain. set_delta (.001) ⇒ không đưa
  phiên quản trị hợp lệ vào.

**Persistence (.002/.003):** `{kind, location}` — kind theo nhãn của đề (run_key, service,
scheduled_task, wmi, startup, systemd, cron…), location là đường dẫn/khoá registry chuẩn hoá.

**.003 — chân dung trọn vẹn:** `vector` = đường vào ban đầu (phishing, khai thác dịch vụ phơi ra ngoài,
thông tin đăng nhập hợp lệ, …); `attck[]` = technique ID của các giai đoạn đã chứng minh. Case đã khép
nhưng **phần kết luận bị cắt** — tự dựng lại từ hiện vật, không suy từ tên case.

## Bẫy hay gặp

- Map theo tên tool thay vì ý đồ của lệnh; bỏ qua sub-technique.
- Liệt kê technique không có bằng chứng ở .003.
- Coi mọi logon type 3 là lateral (máy quản trị, jump host, SCCM/Ansible là hợp lệ).
- Đảo chiều cạnh `src`/`dst`.
