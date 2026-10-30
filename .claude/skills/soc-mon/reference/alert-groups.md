# MON · Phân biệt lành tính vs độc hại — T1348 (13 subtask, 10 nhóm cảnh báo)

Phân biệt cảnh báo thật với cảnh báo giả là việc **chiếm phần lớn thời gian Tier 1**. Threat Hunting và
Compromised Assessment còn phải phân biệt phần mềm hợp lệ với mã độc nguỵ trang (`svch0st.exe` giả
`svchost.exe`, `ssdd` giả `sshd`). Đầu ra: nhãn TP/FP cho từng cảnh báo. FP không tính vào SLA sự cố
nhưng **vẫn tính vào SLA xử lý cảnh báo**.

**Tỉ lệ nền là thiên về FP.** Dữ liệu Monitor đã sinh cho 10 nhóm có tổng cộng ~4 case TP và ~31 case
FP. Đừng mặc định TP; mỗi nhóm có **mẫu âm bắt buộc** — học thuộc chúng.

## T1348.001–.003 — tiến trình và hoạt động quản trị

| Subtask | Mode | Đầu vào | Phải nộp | Chấm |
|---|---|---|---|---|
| **.001** | file | HV-15 | `masquerading[]` tên tiến trình giả mạo | set_delta |
| **.002** | file | HV-15, HV-40 | `labels{}` hợp lệ/tấn công cho từng hoạt động quản trị | accuracy |
| **.003** | soc (EDR) | HV-15 16 17 26 40 | `labels{}` | **macro-average accuracy trên 5 tầng** |

- **.001 nguỵ trang tên hệ thống:** so từng tên với tên hệ thống thật — thay ký tự (`0`↔`o`,
  `1`↔`l`, `rn`↔`m`), thêm/bớt ký tự (`svchosts.exe`, `lsas.exe`), đúng tên nhưng **sai đường dẫn**
  (`svchost.exe` ngoài `C:\Windows\System32`), sai tiến trình cha (svchost không do `services.exe` sinh).
  Process được chuẩn hoá về basename chữ thường. set_delta: mỗi tên lành tính báo nhầm trừ nặng.
- **.002 whitelist nội bộ (HV-40):** hoạt động quản trị khớp whitelist (đúng tài khoản, đúng máy
  nguồn, đúng công cụ, đúng lịch) ⇒ hợp lệ; lệch bất kỳ chiều nào ⇒ xét kỹ, không tự động hợp lệ.
- **.003 phân tầng 5 loại hoạt động:** PsExec · WMI · PowerShell remoting · script hàng loạt · tác vụ
  định kỳ. Điểm là trung bình **theo tầng**, nên tầng hiếm quan trọng bằng tầng đa số — đừng dồn công
  vào loại phổ biến. Đã có hồ sơ mẫu `T1348_0001`.

## T1348.004–.013 — 10 nhóm cảnh báo (cùng khung chấm)

Mọi bài trong nhóm: **mode soc**, chấm `(0.35·classification + 0.25·verdict + Σ trường riêng) × CITE`.

- `classification` ∈ {`INCIDENT`, `SUSPICIOUS`, `NO_IMPACT`} — mức tác động: **INCIDENT** = độc hại và
  đã có tác động/thành công; **SUSPICIOUS** = dấu hiệu độc hại nhưng chưa xác nhận tác động; **NO_IMPACT**
  = lành tính, hoặc thử nhưng không thể thành công.
- `verdict` ∈ {`TP`, `FP`} — cảnh báo có đúng bản chất độc hại không.
- `citations[]` — gate CITE: ≥1 evidence ID thật, 0 ID bịa.
- Mức hiện vật quyết định + ngữ cảnh làm được bằng file tĩnh; mức trọn case cần dựng hệ thống thật
  (`BLOCKED_INTEGRATION`).

| Bài | Nhóm (`GROUP`) | Căn cứ phân biệt (nguồn) | Mẫu âm bắt buộc | Trường riêng (trọng số) |
|---|---|---|---|---|
| **.004** | Mã độc `MALWARE` | hash + **nội dung file**, không dừng ở tên phát hiện AV | công cụ quản trị bị AV gắn PUA (PsExec, NirSoft) · phần mềm đóng gói packer thương mại · file **EICAR** của đợt kiểm thử | `family` alias 0.25 · `artifact_sha256` 0.15 |
| **.005** | Email phishing / lộ lọt TK `PHISHING_EMAIL` | header/URL email + **có click không** + có đăng nhập bất thường sau click không | email marketing hợp lệ · chiến dịch phishing giả lập của chính khách hàng · đăng nhập IP lạ do nhân viên công tác qua VPN | `clicked` 0.15 · `compromised_accounts[]` F2 0.25 |
| **.006** | Scan port `PORT_SCAN` | nguồn quét có trong danh mục scanner/whitelist và **đúng lịch quét** không | Nessus/Qualys nội bộ quét theo lịch · health-check giám sát (Zabbix, load-balancer probe) | `scanner_src` IP 0.2 · `scan_type` ngang/dọc/khối 0.2 |
| **.007** | Scan, khai thác lỗ hổng phần mềm `VULN_EXPLOIT` | payload trong PCAP + **phiên bản trên tài sản đích** + có hành vi hậu khai thác không | payload bắn vào máy **đã vá hoặc sai nền tảng** (thử nhưng không thể thành công) · pentest có phép | `cve` 0.10 · `target_vulnerable` 0.15 · `exploit_succeeded` 0.15 |
| **.008** | Khai thác ứng dụng web `WEB_APP_EXPLOIT` | **mã HTTP trả về** + file/DB có thay đổi thật sau request không | scanner web bị 403/404 · request hợp lệ chứa ký tự đặc biệt (ô tìm kiếm) · file PHP của framework giống webshell | `attack_type` SQLi/XSS/RCE/upload/LFI 0.10 · `request_succeeded` 0.15 · `is_webshell` 0.15 |
| **.009** | Credential `CREDENTIAL_ACCESS` | chuỗi **4625→4624** / truy cập **lsass** + tài khoản có đặc quyền không + có đăng nhập thành công không | user gõ sai mật khẩu nhiều lần · service account dùng mật khẩu hết hạn lặp lại · agent AV/backup đọc lsass hợp lệ | `technique` brute force/spray/kerberoast/dump 0.2 · `accounts[]` 0.2 |
| **.010** | Net IOC `NET_IOC` | **chất lượng IOC** + tiến trình nào mở kết nối + có beacon/truyền dữ liệu không | IOC là IP CDN/cloud dùng chung · domain đã sinkhole · IOC hết hạn · sandbox email tự mở URL | `ioc_status` còn hiệu lực/hết hạn/hạ tầng dùng chung 0.2 · `process` 0.2 |
| **.011** | Tunneling `TUNNELING` | **độ dài/entropy** truy vấn + lưu lượng ra + tiến trình tạo kênh | DNS dài hợp lệ của AV cloud lookup/telemetry · bản ghi TXT xác thực domain · VPN/SSH của quản trị viên | `protocol` DNS/ICMP/HTTP/SSH -R 0.2 · `tunnel_endpoint` 0.2 |
| **.012** | Persistence `PERSISTENCE` | **mục khởi động** + binary nó trỏ tới + **tiến trình đã tạo ra mục đó** | tác vụ cập nhật phần mềm (GoogleUpdate, OneDrive) · cron certbot/logrotate · service agent backup | `mechanism` run_key/service/task/wmi/cron/systemd 0.2 · `creator_process` 0.2 |
| **.013** | Lateral movement `LATERAL_MOVEMENT` | **logon type 3/10** + công cụ thực thi + nguồn có phải jump host được phép không | quản trị viên đi từ jump host/PAM · SCCM/Ansible triển khai hàng loạt · script quản trị theo lịch | `edges[]` {src,dst,account} 0.25 · `tool` PsExec/WMI/WinRM/RDP/SMB 0.15 |

### Cách đọc từng nhóm (thao tác nghề)

- **MALWARE:** tên AV chỉ là gợi ý. Đối chiếu sha256 với HV-34/HV-40; mở nội dung/metadata (chữ ký,
  packer, chuỗi). EICAR có chuỗi chuẩn đã biết ⇒ test, không phải sự cố. PUA quản trị có chữ ký hợp lệ +
  dùng bởi admin ⇒ FP. `artifact_sha256` = hash của **hiện vật quyết định**, không phải hash bất kỳ.
- **PHISHING:** ba câu hỏi tuần tự — email có độc (SPF/DKIM/DMARC, domain giả mạo, URL)? người dùng
  **có click** (proxy/DNS HV-23, HV-27)? **sau click có đăng nhập bất thường** (HV-26, HV-30)? Chỉ tài
  khoản có đăng nhập bất thường sau click mới vào `compromised_accounts` (F2 ⇒ đừng bỏ sót).
- **PORT_SCAN:** so IP nguồn với danh mục scanner (HV-40/HV-38) **và lịch quét**; scanner nội bộ quét
  ngoài lịch vẫn đáng ngờ. `scan_type`: *ngang* = 1 cổng trên nhiều host; *dọc* = nhiều cổng trên 1
  host; *khối* = nhiều cổng trên nhiều host.
- **VULN_EXPLOIT:** đúng CVE trong payload **và** phiên bản đích dễ tổn thương (HV-12, HV-38) **và** có
  hậu khai thác (tiến trình con lạ HV-15, kết nối ra HV-17). Thiếu một trong ba ⇒ thường không phải
  INCIDENT. Nguồn xếp "máy đã vá/sai nền tảng" và "pentest có phép" là **mẫu âm** ⇒ `NO_IMPACT`; quy ước
  `verdict` cho "tấn công thật nhưng không thể thành công" chưa được adjudicate — theo nguồn (mẫu âm) và
  ghi lý do trong trích dẫn.
- **WEB_APP_EXPLOIT:** 403/404 ⇒ request không thành công; 200 + **thay đổi thật** (file mới HV-18, query
  DB HV-31, tiến trình web sinh shell HV-15) ⇒ thành công. Ký tự `' " < >` trong ô tìm kiếm không phải
  tấn công. File PHP framework có `eval` ≠ webshell — kiểm hash với bản phát hành gốc.
- **CREDENTIAL:** nhiều 4625 rồi **4624 thành công** trên cùng tài khoản ⇒ nghi brute force thành công;
  nhiều tài khoản × ít lần mỗi tài khoản ⇒ spray; TGS cho nhiều SPN ⇒ kerberoast; tiến trình không
  phải AV/backup mở handle lsass ⇒ dump. Service account lặp lỗi mật khẩu hết hạn ⇒ FP.
- **NET_IOC:** IOC khớp chưa đủ — kiểm IOC còn hiệu lực (HV-35), có phải hạ tầng dùng chung, tiến trình
  nào kết nối (trình duyệt vs binary lạ), có **beacon đều/khối dữ liệu ra** không.
- **TUNNELING:** subdomain dài + entropy cao + nhiều truy vấn TXT/NULL tới một domain + bytes ra lớn
  ⇒ DNS tunnel; `ssh -R` tới host ngoài ⇒ reverse tunnel. AV cloud lookup cũng dài nhưng tới domain
  của hãng AV đã biết.
- **PERSISTENCE:** ba thứ phải cùng hợp lệ — mục khởi động, binary đích (chữ ký, đường dẫn), **tiến
  trình tạo ra mục** (installer/updater hợp lệ hay shell/script lạ).
- **LATERAL:** logon type 3 (network) / 10 (RDP) từ máy **không phải** jump host/PAM, kèm công cụ thực
  thi từ xa, ngoài lịch quản trị ⇒ nghi lateral. `edges` là cặp có hướng {src, dst, account}.

## Bẫy hay gặp

- Dùng tên rule/tên AV làm kết luận.
- Bỏ qua mẫu âm bắt buộc của nhóm — mỗi nhóm được thiết kế để đánh vào đúng một kiểu FP.
- `classification` và `verdict` mâu thuẫn nhau không có lý do (vd INCIDENT + FP).
- Không trích dẫn hoặc trích ID không tồn tại ⇒ ×0.
