# HUNT · Phát hiện, phân tích xâm nhập và khoanh phạm vi

## Phát hiện các vụ xâm nhập

Tìm dấu vết xâm nhập trên endpoint, máy chủ ứng dụng, database, máy chủ hạ tầng — **kể cả xâm nhập chỉ còn để
lại bằng chứng từng xảy ra trong quá khứ**. Đầu ra: có hay không xâm nhập, và ở đâu.

**Dấu vết xâm nhập trên một máy:** persistence lạ · binary độc (hash) · tiến trình bất thường · đăng nhập bất
thường · webshell hoặc request khai thác trong log web.

**Dấu vết quá khứ:** tệp đã bị xoá nhưng còn **log AV** (đã phát hiện/đã xử lý) và **prefetch** (chứng minh binary
từng chạy), event log cũ ⇒ máy đó **vẫn là máy bị xâm nhập**. Đừng loại vì "không còn thấy tệp".

**Máy sạch nhiều nhiễu:** phần mềm quản trị, agent backup tạo nhiều hoạt động trông giống tấn công nhưng khớp
whitelist ⇒ không đưa vào. Mỗi máy đưa vào phải có bản ghi chứng minh.

```json
{"compromised": ["ws-07", "srv-app-02"], "evidence": ["…"],
 "note": "ws-07: tệp đã xoá, còn log AV 'quarantine failed' + prefetch AGENTD.EXE"}
```

## Phân tích xâm nhập theo Cyber Kill Chain

Phân tích **chuỗi hành vi bất thường và TTP**, không dừng ở IOC/signature. Kill Chain: **Reconnaissance →
Weaponization → Delivery → Exploitation → Installation → Command & Control → Actions on Objectives**.

1. **Sắp sự kiện theo giai đoạn**: dùng logic nhân quả trước (phải có delivery trước exploitation), timestamp là
   phụ — timestamp có thể bị xáo hoặc bị sửa. Giữ đủ mọi sự kiện.
2. **Gán giai đoạn cho từng sự kiện.**
3. Với **trọn một case** (kể cả ảnh bộ nhớ): xác định **đường vào** (`vector`), **timeline** các mốc chính (chuẩn
   hoá UTC — xem `soc-ir`; lệch quá 5 phút coi là sai mốc), **phạm vi** host bị ảnh hưởng, và **kết luận mã độc** từ
   báo cáo phân tích + ảnh bộ nhớ (tiến trình bị inject, kết nối chỉ có trong RAM).

```json
{"kill_chain_order": ["evt-04", "evt-11", "evt-02", "…"],
 "stage": {"evt-04": "Delivery", "evt-11": "Exploitation"},
 "vector": "phishing", "timeline": [{"t": "2026-10-17T03:12:00Z", "event": "evt-04"}],
 "scope": ["ws-07"], "malware_verdict": "malicious"}
```

## Tìm chỉ dấu xâm nhập và dấu vết chống điều tra

Chủ động tìm dấu hiệu xâm nhập trên **toàn bề mặt tấn công**: endpoint (máy chủ, máy trạm, thiết bị OT), lưu
lượng mạng, email, log Firewall/Proxy/SIEM.

**Trích IOC** theo sáu loại (`ipv4`, `domain`, `url`, `sha256`, `email`, `cve`): refang (`hxxp`, `[.]`), chữ thường;
bỏ IP private và domain lành tính/của tổ chức; không ghi host của URL hay domain của email vào `domain`; không coi
tên tệp (`gate.php`) là domain. Chi tiết chuẩn hoá: `../../soc-cnt/reference/coverage-intel.md`.

**Dấu vết chống điều tra** — ghi `{kind, location}`:

| Kiểu | Dấu hiệu |
|---|---|
| xoá event log | Security **1102** (audit log cleared), System 104; khoảng trống log trùng lúc tấn công |
| vô hiệu hoá EDR/AV | service EDR dừng/đổi kiểu khởi động, exclusion lạ, agent ngừng gửi dữ liệu |
| sửa timestamp | mtime/ctime **lùi** về trước thời điểm hợp lý; lệch giữa các nguồn thời gian |
| xoá lịch sử / shadow copy | `.bash_history` bị xoá hoặc `HISTFILE=/dev/null`; `vssadmin delete shadows` |

Hành vi chống điều tra tự nó là chỉ dấu mạnh — báo cả khi không còn payload. Trên trọn một đợt săn: gộp IOC +
dấu vết chống điều tra + timeline thành một bức tranh.

```json
{"ioc": {"ipv4": ["…"], "domain": [], "url": [], "sha256": [], "email": [], "cve": []},
 "antiforensics": [{"kind": "log_cleared", "location": "Security.evtx (1102)"},
                   {"kind": "edr_disabled", "location": "service EdrAgent"}],
 "timeline": ["…"]}
```

## Khoanh phạm vi bị xâm phạm

Xác định toàn bộ **máy trạm, máy chủ và tài khoản** đã bị chiếm quyền hoặc bị ảnh hưởng — đầu ra là **bản đồ
phạm vi bị xâm phạm**.

- **Tài khoản bị chiếm:** đăng nhập thành công bất thường sau chuỗi thất bại (brute force/spray), từ nguồn/giờ/máy
  lạ, logon type lạ với tài khoản đó, dùng để di chuyển ngang; tài khoản mới do attacker tạo.
- **Máy bị xâm phạm:** thêm log biên — máy có kết nối C2/VPN lạ/proxy bất thường, máy là đích của tài khoản bị chiếm.
- **Ba mức** (hai mức đầu dẫn tới **hai kế hoạch xử lý khác hẳn nhau** — dựng lại máy/đổi mật khẩu vs điều tra thêm):

| Mức | Nghĩa | Bằng chứng điển hình |
|---|---|---|
| `bị_kiểm_soát` | attacker thực thi được trên máy / dùng được tài khoản | phiên đăng nhập thành công + thực thi, C2 từ máy, persistence đã cài |
| `bị_chạm` | attacker có tương tác nhưng chưa thấy kiểm soát | truy cập share/tệp, kết nối tới được nhưng không thấy thực thi |
| `chỉ_bị_dò` | chỉ bị quét/thử, không truy cập thành công | port scan, đăng nhập thất bại |

Gán mức theo bằng chứng chứng minh được; không chắc thì chọn mức mà bằng chứng đỡ được, không "đôn" lên.

```json
{"hosts": ["ws-07", "srv-file-01"], "accounts": ["an.nv"],
 "level": {"ws-07": "bị_kiểm_soát", "srv-file-01": "bị_chạm", "an.nv": "bị_kiểm_soát"}}
```

## Sai lầm thường gặp

- Bỏ máy chỉ còn dấu vết quá khứ.
- Đưa máy quản trị/backup nhiều nhiễu vào danh sách xâm nhập.
- Sắp Kill Chain thuần theo timestamp khi timestamp bị xáo/sửa.
- Đếm một domain hai lần, đưa IP private vào IOC.
- Gán `bị_kiểm_soát` cho máy chỉ bị quét.

Nguồn nghiệp vụ: NICE T1102, T1103, T2013, T2016 (catalog SABER).
