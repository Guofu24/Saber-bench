# MON · Phân biệt lành tính và độc hại theo nhóm cảnh báo

Phân biệt cảnh báo thật với cảnh báo giả chiếm **phần lớn thời gian** của Tier 1. Thực tế đa số cảnh báo là
FP (trong dữ liệu vận hành mẫu: khoảng 4 TP trên hơn 30 FP ở 10 nhóm cảnh báo) — đừng mặc định là tấn công,
nhưng cũng không được bỏ lọt cái thật. Mỗi nhóm có những **FP kinh điển** — học thuộc chúng.

## Thang kết luận dùng chung cho mọi nhóm

| Trường | Giá trị | Nghĩa |
|---|---|---|
| `classification` | `INCIDENT` | độc hại và đã có tác động/đã thành công |
| | `SUSPICIOUS` | có dấu hiệu độc hại nhưng chưa xác nhận tác động |
| | `NO_IMPACT` | lành tính, hoặc có thử nhưng không thể thành công |
| `verdict` | `TP` / `FP` | cảnh báo có đúng bản chất độc hại không |
| `explain` | ID bản ghi | bằng chứng cho kết luận |

Hai trường phải khớp nhau về logic (không có `INCIDENT` + `FP`). Kết luận ở mức hiện vật (tệp, gói tin) làm
được bằng dữ liệu tĩnh; xác nhận tác động thật trên cả hệ thống cần điều tra trọn case.

## Mười nhóm cảnh báo

### Mã độc (`MALWARE`)
- **Dựa vào:** hash + **nội dung tệp** — tên phát hiện của AV chỉ là gợi ý.
- **Kiểm:** hash so với báo cáo phân tích mã độc và whitelist; chữ ký số, packer, chuỗi đáng ngờ; tiến trình
  và kết nối mà tệp tạo ra.
- **FP kinh điển:** công cụ quản trị bị AV gắn PUA (PsExec, NirSoft); phần mềm đóng gói bằng packer thương
  mại; **tệp EICAR** của đợt kiểm thử AV.
- **Ghi thêm:** `family` (tên họ theo bảng alias, vì mỗi hãng đặt tên khác), `artifact_sha256` (hash của
  **tệp quyết định** kết luận).

### Email phishing / lộ lọt tài khoản (`PHISHING_EMAIL`)
- **Ba câu hỏi theo thứ tự:** email có độc không (SPF/DKIM/DMARC, domain giả mạo, URL)? Người dùng **có click**
  không (log proxy/DNS)? Sau click **có đăng nhập bất thường** không (AD, cloud)?
- **FP kinh điển:** email marketing hợp lệ; **chiến dịch phishing giả lập của chính khách hàng**; đăng nhập từ
  IP lạ do nhân viên công tác qua VPN.
- **Ghi thêm:** `clicked`, `compromised_accounts` — chỉ tài khoản có đăng nhập bất thường sau click; đừng bỏ
  sót ai.

### Dò quét cổng (`PORT_SCAN`)
- **Dựa vào:** nguồn quét có nằm trong danh mục scanner/whitelist **và đúng lịch quét** không.
- **FP kinh điển:** Nessus/Qualys nội bộ quét theo lịch; health-check giám sát (Zabbix, probe của load balancer).
  Scanner nội bộ quét **ngoài lịch** vẫn đáng ngờ.
- **Ghi thêm:** `scanner_src` (IP nguồn), `scan_type`: *ngang* = một cổng trên nhiều host; *dọc* = nhiều cổng
  trên một host; *khối* = nhiều cổng trên nhiều host.

### Quét, khai thác lỗ hổng phần mềm (`VULN_EXPLOIT`)
- **Cần đủ ba:** payload khai thác trong PCAP **và** phiên bản trên tài sản đích dễ tổn thương (ticket lỗ hổng,
  danh mục tài sản) **và** có hành vi hậu khai thác (tiến trình con lạ, kết nối ra). Thiếu một trong ba thì
  thường chưa phải sự cố.
- **FP kinh điển:** payload bắn vào máy **đã vá hoặc sai nền tảng** (thử nhưng không thể thành công); **pentest
  có phép**. Coi đây là mẫu không gây tác động (`NO_IMPACT`) và ghi rõ lý do.
- **Ghi thêm:** `cve`, `target_vulnerable`, `exploit_succeeded`.

### Khai thác ứng dụng web (`WEB_APP_EXPLOIT`)
- **Dựa vào:** **mã HTTP trả về** + tệp/CSDL **có thay đổi thật** sau request không. 403/404 ⇒ không thành
  công; 200 + tệp mới/truy vấn CSDL lạ/tiến trình web sinh shell ⇒ thành công.
- **FP kinh điển:** scanner web bị chặn 403/404; request hợp lệ chứa ký tự đặc biệt (ô tìm kiếm); tệp PHP của
  framework trông giống webshell — so hash với bản phát hành gốc.
- **Ghi thêm:** `attack_type` (SQLi/XSS/RCE/upload/LFI), `request_succeeded`, `is_webshell`.

### Tấn công thông tin đăng nhập (`CREDENTIAL_ACCESS`)
- **Dựa vào:** chuỗi **4625 → 4624** (thất bại rồi thành công), truy cập **lsass**, tài khoản có đặc quyền
  không, có đăng nhập thành công không.
- **Nhận dạng:** nhiều lần thất bại một tài khoản rồi thành công ⇒ brute force; nhiều tài khoản × ít lần mỗi
  tài khoản ⇒ spray; yêu cầu vé dịch vụ cho nhiều SPN ⇒ kerberoast; tiến trình lạ mở handle lsass ⇒ dump.
- **FP kinh điển:** người dùng gõ sai mật khẩu nhiều lần; service account dùng mật khẩu đã hết hạn lặp lại;
  agent AV/backup đọc lsass hợp lệ.
- **Ghi thêm:** `technique`, `accounts`.

### IOC mạng (`NET_IOC`)
- **Dựa vào:** **chất lượng IOC** (còn hiệu lực? hạ tầng dùng chung?) + tiến trình nào mở kết nối + có beacon/
  truyền dữ liệu không.
- **FP kinh điển:** IP CDN/cloud dùng chung; domain đã sinkhole; IOC hết hạn; sandbox email tự mở URL.
- **Ghi thêm:** `ioc_status` (còn hiệu lực / hết hạn / hạ tầng dùng chung), `process`.

### Tunneling (`TUNNELING`)
- **Dựa vào:** độ dài/entropy truy vấn + lưu lượng ra + tiến trình tạo kênh. Subdomain dài, entropy cao, nhiều
  truy vấn TXT/NULL tới một domain, byte ra lớn ⇒ DNS tunnel; `ssh -R` tới host ngoài ⇒ reverse tunnel.
- **FP kinh điển:** DNS dài hợp lệ của AV cloud lookup/telemetry; bản ghi TXT xác thực domain; VPN/SSH của
  quản trị viên.
- **Ghi thêm:** `protocol` (DNS/ICMP/HTTP/SSH -R), `tunnel_endpoint`.

### Persistence (`PERSISTENCE`)
- **Ba thứ phải cùng hợp lệ:** mục khởi động, **binary nó trỏ tới** (chữ ký, đường dẫn), **tiến trình đã tạo ra
  mục đó** (installer/updater hợp lệ hay shell/script lạ).
- **FP kinh điển:** tác vụ cập nhật phần mềm (GoogleUpdate, OneDrive); cron certbot/logrotate; service của agent
  backup.
- **Ghi thêm:** `mechanism` (run_key/service/task/wmi/cron/systemd), `creator_process`.

### Di chuyển ngang (`LATERAL_MOVEMENT`)
- **Dựa vào:** logon type **3** (network) / **10** (RDP) + công cụ thực thi từ xa + nguồn có phải **jump host/PAM
  được phép** không + có trong lịch quản trị không.
- **FP kinh điển:** quản trị viên đi từ jump host/PAM; SCCM/Ansible triển khai hàng loạt; script quản trị theo lịch.
- **Ghi thêm:** `edges` — cạnh có hướng `{src, dst, account}`; `tool` (PsExec/WMI/WinRM/RDP/SMB).

## Tiến trình nguỵ trang và hoạt động quản trị

**Tiến trình giả tên hệ thống** (`svch0st.exe` giả `svchost.exe`, `ssdd` giả `sshd`):
- thay ký tự (`0`↔`o`, `1`↔`l`, `rn`↔`m`), thêm/bớt ký tự (`svchosts.exe`, `lsas.exe`);
- **đúng tên nhưng sai đường dẫn** (svchost ngoài `C:\Windows\System32`);
- **sai tiến trình cha** (svchost không do `services.exe` sinh ra).

**Gán nhãn hợp lệ/tấn công cho hoạt động quản trị:** khớp whitelist nội bộ ở **mọi chiều** (tài khoản, máy
nguồn, công cụ, lịch) ⇒ hợp lệ; lệch một chiều ⇒ xem kỹ. Xét riêng từng loại hoạt động — **PsExec · WMI ·
PowerShell remoting · script hàng loạt · tác vụ định kỳ** — vì loại hiếm cũng quan trọng như loại phổ biến;
đừng để thói quen của loại đa số quyết định thay.

```json
{"masquerading": ["svch0st.exe", "lsas.exe"],
 "labels": {"ACT-12": "hợp lệ", "ACT-13": "tấn công", "ACT-14": "hợp lệ"}}
```

## Sai lầm thường gặp

- Lấy tên rule/tên AV làm kết luận.
- Bỏ qua FP kinh điển của nhóm — mỗi nhóm có đúng những kiểu FP được liệt kê ở trên.
- `classification` và `verdict` mâu thuẫn mà không giải thích.
- Kết luận không kèm ID bản ghi chứng minh.

Nguồn nghiệp vụ: NICE T1348 (catalog SABER).
