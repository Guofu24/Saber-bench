# DFIR · Windows, Linux và macOS

Đầu vào: OS/build, host ID/role, time window, coverage và artifacts được cấp.
Đầu ra: execution/session/persistence/file/network chain có record refs, baseline và khoảng thiếu.
Không suy ra danh tính người thao tác chỉ từ account hoặc file owner.

## Windows

| Câu hỏi | Nguồn/pivot | Bẫy cần tránh |
|---|---|---|
| Ai xác thực, ở đâu? | Security 4624/4625, 4648, 4672; SID/domain, logon ID, host, source, logon type | Type 3 là network logon, không tự là lateral movement; 4672 không tự là chiếm domain |
| Tiến trình nào chạy? | 4688, Sysmon 1, EDR, Prefetch; image/hash, ProcessGUID hoặc PID + start + host | PID tái sử dụng; 4688 command line cần policy; không có Prefetch không phủ định execution |
| Persistence nào? | 4698/task XML; 4697/System 7045/services; Run/RunOnce/startup; WMI filter + consumer + binding | Tên lạ/unsigned là đầu mối; task/service quản trị hợp lệ cần change record |
| File tồn tại hay được dùng? | MFT/USN, LNK/Jump Lists, browser download, registry, SRUM | Metadata khác nội dung; LNK/USB không tự chứng minh sao chép/exfil |
| Log bị tác động? | Security 1102, audit/config changes, Sysmon state/config, EDR tamper, log gaps | Gaps có thể do outage/retention; log clear không xác định toàn bộ nội dung đã mất |
| Ra mạng/di chuyển ngang? | Sysmon 3/22, RDP operational, DC auth, SMB/firewall/EDR | DNS query khác kết nối; cần nối host nguồn/đích và hành vi trái phép |

Registry lấy hive và transaction logs liên quan khi phương pháp cho phép; ghi live hay offline,
parser/version và trạng thái replay. Đường dẫn `CurrentControlSet` trong hướng dẫn live không được áp máy móc
cho ảnh offline: xác minh active control set từ hive `SYSTEM`, giữ thông tin chọn set trong báo cáo.
Không load/replay để sửa bản hive gốc. Với WMI, kiểm cả filter, consumer, binding và baseline quản trị.

Diễn giải artifact theo OS/parser:

- Prefetch hỗ trợ execution trên hệ có ghi nhận; không tự chỉ ra user, ý định hoặc toàn bộ command line.
- Amcache là inventory/metadata; Shimcache phụ thuộc phiên bản, không tự chứng minh execution tại timestamp đó.
- BAM/DAM và SRUM không phải lịch sử đầy đủ; ghi retention/availability thực tế.
- MFT/USN dùng để liên hệ file IDs, path và thay đổi; timestamp có thể bị đổi, journal có thể wrap.
- LNK/Jump Lists/browser/USB hỗ trợ hoạt động người dùng; cần audit/process/content evidence cho assertion mạnh hơn.
- Binary signer và AV result là enrichment, không đủ để kết luận an toàn hoặc đã thực thi malware.

## Linux

1. Xác định distro/kernel, filesystem, boot ID, host/container namespace, clock, logging/rotation.
2. Live process/socket/session khi có tool; correlate `/proc`, journal, auth/secure, sudo, auditd,
   web/app logs và network telemetry. Record audit event identity/serial, không chỉ grep một dòng.
3. Review systemd units/timers, cron, SSH authorized keys/config, shell startup và writable paths;
   so package/deploy/config-management history. Ghi owner, target command/hash và mốc thay đổi.
4. Timeline phân biệt mtime/ctime/atime; ctime không phải creation time. History có thể chưa flush,
   không có timestamp, dùng shell khác hoặc bị sửa. `last` phụ thuộc wtmp, không thay auth logs.
5. Nếu nghi rootkit/tamper, giữ kết quả live như nguồn có giới hạn và corroborate ngoài host;
   không tự cài scanner hoặc gỡ thành phần chỉ để kiểm chứng.

## macOS

Thu đúng phạm vi Unified Log/logarchive, EDR/MDM, LaunchAgents/LaunchDaemons/Login Items,
quarantine, browser và filesystem metadata/APFS/FSEvents khi có. Xác định build, FileVault,
TCC/privacy permissions và công cụ hỗ trợ trước khi hứa acquisition.
Chữ ký/notarization không loại trừ lạm dụng; launch item có thể do MDM/phần mềm hợp lệ.
Giải thích timestamp/record theo parser và phiên bản; không tắt SIP/TCC trên máy live để vượt giới hạn.

## Mẫu chốt host

```text
host_id / OS-build / role / owner / case / time-range
coverage: nguồn, policy, retention, gaps, clock
execution: process-identity -> parent -> command/hash -> session -> file/network evidence
persistence: type, location, target, creator/change evidence, benign alternative
scope: confirmed/suspected/unknown + evidence; related hosts/accounts
limitations / next collection / IR handoff / reviewer
```

Tham chiếu: [Microsoft Sysmon](https://learn.microsoft.com/en-us/sysinternals/downloads/sysmon),
[Microsoft logon events](https://learn.microsoft.com/en-us/previous-versions/windows/it-pro/windows-10/security/threat-protection/auditing/basic-audit-logon-events),
[SANS Windows Playbook](https://www.sans.org/posters/windows-forensic-analysis-playbook).
