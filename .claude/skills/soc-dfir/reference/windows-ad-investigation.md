# DFIR · Điều tra Windows/AD theo chuỗi sự kiện

Chọn khi cần đi từ alert/logon tới execution, lateral movement hoặc thay đổi danh tính/trust.
Input: raw EVTX/EDR/DC records, host/DC identity, OS/event version, audit policy/SACL và time coverage.

## Lập đồ thị có khóa đúng

Lưu provider + channel + computer + event record ID + time, không dùng Event ID làm định danh duy nhất.
Giữ SID/domain, Subject/Target riêng, LogonId có scope host/session; ProcessGuid hoặc PID + lifetime.
Không join chỉ bằng username/IP, và không ghép một logon ở DC với process endpoint chỉ vì LogonId bằng nhau.
Raw XML/EventData giúp tránh lệ thuộc ngôn ngữ Message; field thiếu khác field bằng 0.

| Giả thuyết | Dữ liệu cần nối | Kiểm giải thích đối lập |
|---|---|---|
| Remote execution qua account | Target 4624/4648 + source/target process + network + service/task nếu có | Admin deployment, PAM/jump host, scheduled maintenance |
| Service/task persistence | 7045/4697 hoặc 4698 + config/XML + binary/path/hash + creator/session | Installer/updater; current config không tự chứng minh trạng thái lúc sự cố |
| Kerberos bất thường | 4768/4769/4771 + SPN/account/source/time + downstream endpoint activity | Legacy encryption/service patterns; event count/type không tự chứng minh ticket forgery |
| AD object bị sửa | 5136 object GUID/DN, attribute, operation, correlation + actor + change records | Thay đổi hợp lệ, cặp delete/add của một lần cập nhật |
| Directory access đáng ngờ | 4662 object/properties/access mask + subject/session + source + authorized replication inventory | DC/sync/service hợp lệ; 4662 một mình không chứng minh credential theft |
| WMI persistence | Filter + consumer + binding/config, Sysmon 19/20/21 nếu có + parent/process behavior | Inventory/management tooling, thiếu event do config |

5136 cần audit phù hợp trên object/attribute; thường có Value Deleted và Value Added cho một thay đổi.
4662 cũng phụ thuộc SACL. Không có event không chứng minh object không bị đọc/sửa.
Ghi audit coverage **tại thời điểm sự cố**, không lấy policy mới bật sau đó để suy quá khứ.

## Từ nghi ngờ tới finding

1. Đặt cửa sổ quanh anchor rồi mở rộng theo session/process/resource, không quét mọi log không giới hạn.
2. Lấy raw fields trước; xây graph source host → credential/session → target action. Mọi cạnh có evidence ref.
3. Kiểm clock/NAT/reused PID/shared accounts và legitimate changes. Đánh dấu các cạnh chỉ là giả thuyết.
4. Mở scope theo privileged group/ACL/GPO/delegation/CA/template/trust changes có căn cứ.
   GPO/PKI hiện trạng chỉ là snapshot; cần version/config/audit lịch sử để xác định thời điểm và actor.
5. Phân biệt account abuse, endpoint admin, domain admin, DC compromise và forest-wide trust compromise.
   Chưa đủ dữ liệu thì không chọn mức rộng nhất chỉ vì nguy cơ cao; vẫn escalation nguy cơ cho IR.
6. Handoff identity/IR: entities affected/suspected, quyền liên quan, ongoing sessions, persistence,
   evidence đã giữ, phần cần owner kiểm và rủi ro khi rotate/reset. Không tự thực hiện forest recovery.

## Pivot bằng Defender XDR, chỉ khi bảng và quyền có thật

Mẫu KQL để xem execution trên một device đã xác định; thay ID/time bằng scope được cấp:

```kusto
DeviceProcessEvents
| where Timestamp >= datetime(2026-11-01T00:00:00Z)
    and Timestamp < datetime(2026-11-02T00:00:00Z)
| where DeviceId == "DEVICE_ID_FROM_CASE"
| project Timestamp, DeviceId, DeviceName, ProcessId, ProcessCreationTime,
    FileName, FolderPath, ProcessCommandLine, AccountSid,
    InitiatingProcessId, InitiatingProcessCreationTime, InitiatingProcessFileName
| order by Timestamp asc
```

Network pivot dùng DeviceNetworkEvents với DeviceId và process lifetime liên quan; ghi RemoteIP/RemotePort,
RemoteUrl, ActionType và initiating process fields theo schema thực tế. Đừng tự join hàng triệu rows chỉ bằng PID.
Result caps/sensor offline/retention cần ghi; không có Defender for Endpoint thì bảng có thể không có dữ liệu.

Nguồn: [Microsoft 5136](https://learn.microsoft.com/en-us/previous-versions/windows/it-pro/windows-10/security/threat-protection/auditing/event-5136),
[4662](https://learn.microsoft.com/en-us/previous-versions/windows/it-pro/windows-10/security/threat-protection/auditing/event-4662),
[DeviceProcessEvents](https://learn.microsoft.com/en-us/defender-xdr/advanced-hunting-deviceprocessevents-table),
[DeviceNetworkEvents](https://learn.microsoft.com/en-us/defender-xdr/advanced-hunting-devicenetworkevents-table).
