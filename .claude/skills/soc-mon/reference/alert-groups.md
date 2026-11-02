# MON · Phân biệt lành tính và độc hại theo nhóm cảnh báo

Kiểm chứng từng cảnh báo bằng dữ liệu và ngữ cảnh được cấp. Tỷ lệ TP/FP phụ thuộc môi trường;
không dùng tỷ lệ của bộ mẫu để đoán nhãn. Các ví dụ lành tính dưới đây là giả thuyết cần kiểm tra,
không phải danh sách miễn trừ hay danh sách đầy đủ mọi nguyên nhân FP.

## Tách bản chất hành vi, kết quả và tác động

Trước khi gán nhãn, xác định cảnh báo đang khẳng định **attempt**, **truy cập thành công** hay **tác động**.
Một lần tấn công bị chặn có thể là TP của rule phát hiện attempt nhưng không chứng minh compromise.
Ghi riêng việc có được phép hay không, hành vi quan sát được, kết quả và điều chưa biết.
Nếu case yêu cầu các trường sau, dùng đúng định nghĩa/schema của case:

| Trường | Giá trị | Nghĩa |
|---|---|---|
| `classification` | `INCIDENT` | độc hại và đã có tác động/đã thành công |
| | `SUSPICIOUS` | có dấu hiệu độc hại nhưng chưa xác nhận tác động |
| | `NO_IMPACT` | có bằng chứng phù hợp với tiêu chí case rằng không gây tác động; không đồng nghĩa với không có attempt |
| `verdict` | `TP` / `FP` | khẳng định cụ thể mà rule đưa ra có đúng không |
| `explain` | ID bản ghi | bằng chứng cho kết luận |

Giải thích quan hệ giữa các trường theo cùng phạm vi đánh giá. Không đổi enum của contract hoặc tự thêm trường.
Thiếu telemetry không đủ kết luận `NO_IMPACT`/`FP`; dùng trạng thái chưa xác định nếu schema cho phép,
nếu không thì ghi giới hạn trong phần giải thích và yêu cầu bổ sung qua kênh được cấp.

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
- **Ghi thêm:** `clicked`, `compromised_accounts`. DNS/proxy có thể do scanner email tạo; đăng nhập lạ sau click
  chưa đủ chứng minh tài khoản bị chiếm. Liên kết phiên, thiết bị, người dùng và hành vi trái phép trước khi kết luận.

### Dò quét cổng (`PORT_SCAN`)
- **Dựa vào:** nguồn quét có nằm trong danh mục scanner/whitelist **và đúng lịch quét** không.
- **FP kinh điển:** Nessus/Qualys nội bộ quét theo lịch; health-check giám sát (Zabbix, probe của load balancer).
  Scanner nội bộ quét **ngoài lịch** vẫn đáng ngờ.
- **Ghi thêm:** `scanner_src` (IP nguồn), `scan_type`: *ngang* = một cổng trên nhiều host; *dọc* = nhiều cổng
  trên một host; *khối* = nhiều cổng trên nhiều host.

### Quét, khai thác lỗ hổng phần mềm (`VULN_EXPLOIT`)
- **Đối chiếu:** request/payload, điều kiện khai thác của tài sản và hiệu ứng hậu khai thác. Phiên bản chưa biết
  hoặc thiếu PCAP không phủ định hiệu ứng đã có bằng chứng; thiếu dữ liệu thì ghi chưa xác định.
- **Giả thuyết cần loại trừ:** máy đã vá, sai nền tảng, pentest có phép. Kiểm phiên bản/cấu hình thực tế và
  phạm vi giấy phép; không suy ra không có tác động chỉ từ tên bản vá hay việc được phép kiểm thử.
  Case đánh giá khai thác thành công có thể coi attempt thất bại là âm tính; vẫn giữ thông tin attempt.
- **Ghi thêm:** `cve`, `target_vulnerable`, `exploit_succeeded`.

### Khai thác ứng dụng web (`WEB_APP_EXPLOIT`)
- **Dựa vào:** liên kết request với log ứng dụng, quyền truy cập và thay đổi/truy xuất dữ liệu thực tế.
  HTTP 200 chỉ nói request được xử lý thành công theo HTTP; 403/404 không chứng minh backend không có hiệu ứng.
  Phân biệt attempt bị chặn, thao tác hợp lệ và truy cập/thay đổi trái phép; thiếu log thì chưa xác nhận tác động.
- **Giả thuyết lành tính:** request hợp lệ chứa ký tự đặc biệt (ô tìm kiếm); tệp PHP của
  framework trông giống webshell — so hash với bản phát hành gốc.
- **Ghi thêm:** `attack_type` (SQLi/XSS/RCE/upload/LFI), `request_succeeded`, `is_webshell`.

### Tấn công thông tin đăng nhập (`CREDENTIAL_ACCESS`)
- **Dựa vào:** chuỗi **4625 → 4624** (thất bại rồi thành công), truy cập **lsass**, tài khoản có đặc quyền
  không, có đăng nhập thành công không.
- **Giả thuyết:** nhiều lỗi một tài khoản có thể là brute force; lỗi trải nhiều tài khoản có thể là spray.
  Đối chiếu nguồn, nhịp, logon type, phiên và công việc hợp lệ. 4625 rồi 4624 không tự chứng minh chiếm tài khoản;
  nhiều vé SPN không tự chứng minh kerberoast; mở handle LSASS không tự chứng minh đã dump credential.
- **FP kinh điển:** người dùng gõ sai mật khẩu nhiều lần; service account dùng mật khẩu đã hết hạn lặp lại;
  agent AV/backup đọc lsass hợp lệ.
- **Ghi thêm:** `technique`, `accounts`.

### IOC mạng (`NET_IOC`)
- **Dựa vào:** **chất lượng IOC** (còn hiệu lực? hạ tầng dùng chung?) + tiến trình nào mở kết nối + có beacon/
  truyền dữ liệu không.
- **FP kinh điển:** IP CDN/cloud dùng chung; domain đã sinkhole; IOC hết hạn; sandbox email tự mở URL.
- **Ghi thêm:** `ioc_status` (còn hiệu lực / hết hạn / hạ tầng dùng chung), `process`.

### Tunneling (`TUNNELING`)
- **Dựa vào:** độ dài/entropy truy vấn, chuỗi phiên, lưu lượng và tiến trình tạo kênh. DNS dài/entropy cao chỉ là
  dấu hiệu cần kiểm tra. Xác nhận cơ chế truyền dữ liệu và mục đích; `ssh -R` cho biết remote forwarding,
  chưa cho biết có trái phép hay không.
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
nguồn, công cụ, lịch) hỗ trợ giả thuyết hợp lệ, nhưng vẫn kiểm hành vi thực tế và dấu hiệu tài khoản bị lạm dụng;
lệch một chiều thì điều tra thêm, không tự gán độc hại. Các dấu hiệu tên/path/cha ở trên cũng chỉ là đầu mối.
Xét riêng từng loại hoạt động — **PsExec · WMI ·
PowerShell remoting · script hàng loạt · tác vụ định kỳ** — vì loại hiếm cũng quan trọng như loại phổ biến;
đừng để thói quen của loại đa số quyết định thay.

```json
{"masquerading": ["svch0st.exe", "lsas.exe"],
 "labels": {"ACT-12": "hợp lệ", "ACT-13": "tấn công", "ACT-14": "hợp lệ"}}
```

## Sai lầm thường gặp

- Lấy tên rule/tên AV làm kết luận.
- Coi chữ ký, whitelist, CDN dùng chung hoặc IOC hết hạn là bằng chứng tự động loại trừ tấn công.
- `classification` và `verdict` mâu thuẫn mà không giải thích.
- Kết luận không kèm ID bản ghi chứng minh.

Nguồn nghiệp vụ: NICE T1348 (catalog SABER).
