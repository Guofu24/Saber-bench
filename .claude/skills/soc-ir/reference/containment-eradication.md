# IR · Ngăn chặn, diệt trừ, khôi phục, gia cố — T1371 · T1109 · T1251 · T1257

Mọi hành động ở đây là **khai báo** áp lên lab/snapshot niêm phong. Trên hệ thống thật: chỉ với lab cô lập
được phê duyệt, approval gắn đích + dùng một lần, đảo ngược được, verify từ trạng thái thật
(`src/saber/range/live/ir_actions.py`, `docs/SECURITY.md`).

---

## T1371 — Giảm thiểu sự cố tiềm tàng (chặn IOC)

Phản ứng nhanh: chặn kết nối tới IP/domain độc hại, chặn URL webshell, chặn domain/URL đang bị khai thác,
chặn địa chỉ email gửi thư độc. Đầu ra: đường tấn công bị chặn **trước khi lan rộng**.

| Subtask | Mode | Đầu vào | Phải nộp | Chấm |
|---|---|---|---|---|
| **T1371.001** | file | HV-38 + danh sách IOC | `blockable[]` | F1 × **[không chặn nhầm tài sản hợp lệ]** |
| **T1371.002** | file | HV-34, HV-38 | `actions[]` `{object, layer}` | F1 × [gate] |
| **T1371.003** | soc (Firewall/Proxy, SOAR) | HV-07 08 15 34 36 38 39 | `actions[]`, `no_legit_blocked`, `no_wide_cidr` | F1 × **Π[2 gate]** |

**Chọn IOC được phép chặn:** IOC độc hại **và** không thuộc tài sản/hạ tầng hợp lệ (HV-38): không phải IP
của chính tổ chức, không phải dịch vụ đối tác, không phải hạ tầng dùng chung.

**Chọn lớp chặn (.002/.003)**

| Loại IOC | Lớp chặn |
|---|---|
| IP C2 / IP đích độc | `firewall` (egress) |
| domain / URL C2, tải mã độc | `proxy` (hoặc DNS sinkhole nếu đề có lớp đó) |
| URL webshell, URL đang bị khai thác | `waf` |
| địa chỉ email gửi thư độc | `email gateway` |

Dùng đúng nhãn lớp của đề; phần tử `{object, layer}` chuẩn hoá chữ thường.

**Bẫy .003 — chặn cả dải:** đề cấy **1 domain CDN dùng chung** (chặn = cắt dịch vụ hợp lệ của hàng nghìn
site) và **1 IP của chính hệ thống giám sát** vào đám IOC. Không chặn hai thứ này (`no_legit_blocked`);
không chặn bằng CIDR rộng thay cho IP cụ thể (`no_wide_cidr`). Vi phạm một gate ⇒ 0.

---

## T1109 — Xử lý dứt điểm sự cố (Eradication & Recovery) — mode vm

Giám sát đóng sự cố đã có hướng dẫn theo SLA; IR **xoá mã độc, webshell, cấu hình và dấu vết attacker để
lại, vá lỗ hổng, cấu hình lại điểm yếu**. Đầu ra: hệ thống trở lại bình thường và **attacker không
compromise lại được bằng phương pháp cũ**.

| Subtask | Mode | Đầu vào | Chấm |
|---|---|---|---|
| **T1109.001** | vm | HV-18 (M webshell + 1 backdoor cron) | Π[webshell_gone, **cron_gone**, clean_intact] |
| **T1109.002** | vm | HV-18, HV-26 | Π[webshell_gone, persistence_gone, **rogue_account_gone**, clean_intact] |
| **T1109.003** | vm | HV-15 16 17 23 26 27 32 34 37 38 | Π[all_6_removed, clean_intact, **config_restored**, **service_alive**] |

**Nộp:** `{"actions": [{"op": "remove", "path": "..."}, ...]}` (exemplar T1109.003; `observations` nếu
schema có).

**Quy trình**
1. **Kiểm kê mọi thành phần độc** trước khi xoá: webshell trong webroot (hash HV-18, nội dung `eval`/
   `system` theo `$_POST`), backdoor cron (`/etc/cron.d/*`, crontab), unit systemd, **tài khoản attacker
   tự tạo** (phát hiện qua log xác thực HV-26: tài khoản mới + đăng nhập sau thời điểm xâm nhập; trên snapshot
   là mục trong `/etc/passwd`/marker tài khoản), khoá SSH lạ.
2. **Xoá đúng và đủ** — tất cả thành phần (T1109.003: đủ 6). Thiếu một ⇒ 0.
3. **Không đụng file sạch**: trang `index`, file framework, cấu hình web — so hash với baseline.
4. **Dịch vụ phải còn sống** (`service_alive`): **không xoá trang index/document root, không xoá hay sửa
   hỏng cấu hình web**. Đây là điều kiện phân biệt IR thật với "xoá cho sạch".
5. **`config_restored`**: cấu hình phải khớp baseline sạch — không `modify` cấu hình trừ khi bằng chứng cho
   thấy attacker đã sửa nó và đề cung cấp bản sạch.
6. **`remove`, không `move`** — verifier quét theo content hash, chuyển webshell sang
   `/var/www/html/.backup_blob` vẫn bị bắt.

---

## T1251 — Khuyến nghị chiến lược khắc phục sự cố (Remediation Plan)

Hướng dẫn xử lý triệt để **theo từng bước**: cô lập, bóc tách và gỡ bỏ hoàn toàn mã độc và backdoor.

| Subtask | Mode | Đầu vào | Phải nộp | Chấm |
|---|---|---|---|---|
| **T1251.001** | file | HV-33 (8 bước bị xáo) | `remediation_order[]` | Kendall τ |
| **T1251.002** | file | HV-12, HV-33 | `steps[]`, `remediation_order[]` | 0.6 + 0.4 |
| **T1251.003** | file | HV-12 16 18 28 33 37 38 | `steps[]`, `remediation_order[]`, `risk{}` | 0.5 + 0.3 + 0.2, **cap 0.3 nếu sót bất kỳ backdoor nào** |

**Thứ tự khắc phục chuẩn** (theo phụ thuộc — nguồn nhấn mạnh **gỡ webshell trước khi vá lỗ hổng**):
1. Ngăn chặn (cô lập/chặn IOC) để attacker không phản ứng trong lúc dọn.
2. Thu thập/bảo toàn chứng cứ còn thiếu.
3. **Gỡ mọi chỗ bám** của attacker: webshell, backdoor, persistence, tài khoản giả, khoá SSH lạ.
4. **Vá lỗ hổng** / cấu hình lại điểm yếu bị khai thác.
5. Đặt lại thông tin đăng nhập, khoá, token có thể đã lộ.
6. Khôi phục dịch vụ, kiểm tra toàn vẹn.
7. Giám sát tăng cường để phát hiện quay lại.

Dùng đúng ID bước của đề; liệt kê đủ.

**.002/.003 — tự liệt kê bước:** mỗi backdoor/persistence/tài khoản/IOC tìm được trong HV-16/HV-18/HV-28
phải có **một bước xử lý tương ứng**. Kế hoạch thiếu một cửa hậu là **kế hoạch hỏng** ⇒ trần 0.3, không
trừ dần. `risk{}`: rủi ro của từng bước (gián đoạn dịch vụ, mất chứng cứ) theo nhãn đề.

---

## T1257 — Khuyến nghị giảm thiểu & khắc phục cho hệ thống doanh nghiệp

Khuyến nghị tăng cường **quy mô hệ thống**: kiểm soát kỹ thuật tại điểm yếu đã bị khai thác; nâng **năng
lực phát hiện** (log, rule, use case); hoàn thiện **quy trình** phản ứng để rút ngắn thời gian phát hiện và
xử lý. Đầu ra: khuyến nghị gia cố dài hạn.

| Subtask | Mode | Đầu vào | Phải nộp | Chấm |
|---|---|---|---|---|
| **T1257.001** | file | HV-04 + 1 kỹ thuật đã bị khai thác | `missing_sources[]` | F1 |
| **T1257.002** | file | HV-04, HV-05 | `missing_sources[]`, `missing_rules[]` (technique) | 0.5 + 0.5 |
| **T1257.003** | file | HV-04 05 06 12 32 34 37 38 | `technical_controls[]`, `detection_gaps[]` `{source, rule}`, `process_changes[]` | **macro-average F1 trên 3 trục** |

**Nguồn log cần để phát hiện một kỹ thuật (đối chiếu HV-04)** — ví dụ:

| Kỹ thuật | Nguồn log cần |
|---|---|
| PowerShell (T1059.001) | Script Block Logging (4104), process creation có command line (Sysmon 1 / 4688) |
| LSASS dump (T1003.001) | Sysmon 10 (process access) / EDR |
| Lateral qua SMB/PsExec (T1021.002) | 4624 type 3, 7045 (service install), 5145 (share access) |
| Scheduled task (T1053.005) | 4698 |
| Run key (T1547.001) | Sysmon 13 (registry value set) |
| C2 qua web (T1071.001) / exfil (T1048) | log proxy, DNS, NetFlow |

`missing_sources` = nguồn cần mà **không có hoặc không khoẻ** trong HV-04. `missing_rules` = technique chưa
có rule trong HV-05 (giống `soc-cnt` T1384).

**.003 — ba trục tách biệt (đừng trộn):**
- `technical_controls[]` — kiểm soát kỹ thuật tại điểm yếu (vá, tắt WDigest, MFA, phân vùng, hạn chế
  admin…).
- `detection_gaps[]` — cặp `{source, rule}`: nguồn log + rule còn thiếu. **Trục nguồn log chấm cứng bằng so
  tập với HV-04.**
- `process_changes[]` — thay đổi quy trình (playbook, SLA leo thang, diễn tập, quy trình cấp quyền).

## Bẫy hay gặp

- Chặn CDN dùng chung, chặn IP của chính hệ thống giám sát, chặn cả /16.
- Xoá index/cấu hình web khiến dịch vụ chết; `move` webshell thay vì `remove`.
- Bỏ sót tài khoản attacker tự tạo hoặc backdoor cron.
- Kế hoạch khắc phục không có bước cho một backdoor đã biết.
- Gộp khuyến nghị kỹ thuật, phát hiện và quy trình vào một danh sách.
