# HUNT · Phát hiện, phân tích xâm nhập và khoanh phạm vi

## Phát hiện các vụ xâm nhập

Tìm dấu vết xâm nhập trên endpoint, máy chủ ứng dụng, database, máy chủ hạ tầng — **kể cả xâm nhập chỉ còn để
lại bằng chứng từng xảy ra trong quá khứ**. Đầu ra: có hay không xâm nhập, và ở đâu.

**Dấu vết xâm nhập trên một máy:** persistence lạ · binary độc (hash) · tiến trình bất thường · đăng nhập bất
thường · webshell hoặc request khai thác trong log web.

**Dấu vết quá khứ:** log AV, prefetch và event log có thể hỗ trợ xác nhận xâm nhập đã xảy ra dù tệp đã bị xoá.
Kiểm hash/path, thời gian, kết quả chặn và bằng chứng thực thi: phát hiện/quarantine đơn lẻ không chứng minh
compromise; prefetch cần gắn đúng binary và ngữ cảnh. Tách "từng bị xâm nhập" với "còn bị kiểm soát".

**Máy sạch nhiều nhiễu:** phần mềm quản trị, agent backup tạo nhiều hoạt động trông giống tấn công nhưng khớp
whitelist và hành vi hợp lệ thì có thể loại; không miễn trừ chỉ vì tên/whitelist. Mỗi máy đưa vào phải có bản ghi chứng minh.

```json
{"compromised": ["ws-07", "srv-app-02"], "evidence": ["…"],
 "note": "ws-07: tệp đã xoá, còn log AV 'quarantine failed' + prefetch AGENTD.EXE"}
```

## Phân tích xâm nhập theo Cyber Kill Chain

Phân tích **chuỗi hành vi bất thường và TTP**, không dừng ở IOC/signature. Kill Chain: **Reconnaissance →
Weaponization → Delivery → Exploitation → Installation → Command & Control → Actions on Objectives**.

1. Giữ nguyên timestamp gốc; chuẩn hoá bằng timezone/clock offset có căn cứ. Dùng quan hệ nhân quả để kiểm tra
   thứ tự, không sửa thời gian để ép khớp mô hình. Nếu case yêu cầu thứ tự theo giai đoạn, trình bày riêng với timeline.
2. **Gán giai đoạn có bằng chứng cho từng sự kiện**; một chiến dịch có thể lặp, rẽ nhánh hoặc không quan sát đủ các pha.
3. Với **trọn một case** (kể cả ảnh bộ nhớ): xác định **đường vào** (`vector`), **timeline** các mốc chính (chuẩn
   hoá UTC — xem `soc-ir`; ghi độ chính xác/offset còn chưa rõ), **phạm vi** host bị ảnh hưởng, và **kết luận mã độc** từ
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

**Trích IOC** theo sáu loại (`ipv4`, `domain`, `url`, `sha256`, `email`, `cve`): giữ bản gốc và nguồn, chuẩn hoá theo
loại, phân biệt observable với IOC có căn cứ. Không loại IP nội bộ mặc định hoặc coi tên tệp là domain.
Chi tiết chuẩn hoá: `../../soc-cnt/reference/coverage-intel.md`.

**Dấu vết chống điều tra** — ghi `{kind, location}`:

| Kiểu | Dấu hiệu |
|---|---|
| xoá event log | Security **1102** (audit log cleared), System 104; khoảng trống log trùng lúc tấn công |
| vô hiệu hoá EDR/AV | service EDR dừng/đổi kiểu khởi động, exclusion lạ, agent ngừng gửi dữ liệu |
| sửa timestamp | mtime/ctime **lùi** về trước thời điểm hợp lý; lệch giữa các nguồn thời gian |
| xoá lịch sử / shadow copy | `.bash_history` bị xoá hoặc `HISTFILE=/dev/null`; `vssadmin delete shadows` |

Đối chiếu maintenance/retention và sức khoẻ nguồn log trước khi gán mục đích chống điều tra; khoảng trống log đơn
lẻ chưa chứng minh attacker xoá log. Nếu có căn cứ thì báo cả khi không còn payload. Trên trọn một đợt săn: gộp IOC +
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
  lạ, logon type lạ với tài khoản đó là đầu mối; xác nhận bằng phiên/hành vi trái phép, không chỉ chuỗi fail → success.
  Tài khoản mới phải có bằng chứng attacker tạo, không suy từ thời điểm tạo đơn lẻ.
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
- Ép timeline vào thứ tự Kill Chain hoặc tự sửa timestamp không có căn cứ.
- Đếm hai biểu diễn của cùng observable thành hai bằng chứng; loại IP private mặc định.
- Gán `bị_kiểm_soát` cho máy chỉ bị quét.

Nguồn nghiệp vụ: NICE T1102, T1103, T2013, T2016 (catalog SABER).
