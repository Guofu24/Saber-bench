# HUNT · Phát hiện và phân tích xâm nhập — T1102 · T1103 · T2013 · T2016

---

## T1102 — Phát hiện các vụ xâm nhập

Phát hiện dấu vết xâm nhập trên endpoint, máy chủ ứng dụng, database, máy chủ hạ tầng — **kể cả xâm
nhập chỉ còn để lại bằng chứng từng xảy ra trong quá khứ**. Đầu ra: có hay không xâm nhập, ở đâu.

| Subtask | Mode | Đầu vào | Phải nộp | Chấm |
|---|---|---|---|---|
| **T1102.001** | file | HV-16 artifact của N máy (M bị xâm nhập) | `compromised[]` host | **F2** |
| **T1102.002** | file | HV-14, HV-16 | `compromised[]` | F2 — thêm 1 máy **chỉ còn dấu vết quá khứ** |
| **T1102.003** | vm (12 máy) | HV-15 16 18 26 28 40 | `compromised[]`, `citations[]` | F2 × **CITE** — ≥2 máy sạch nhiều nhiễu |

- **Dấu vết xâm nhập** trên một máy: persistence lạ (HV-16), binary độc (hash HV-18), tiến trình bất
  thường (HV-15), đăng nhập bất thường (HV-26), webshell/request khai thác (HV-28).
- **.002 — dấu vết quá khứ:** file đã bị xoá, chỉ còn **log AV** (HV-14 ghi nhận phát hiện/xử lý) và
  **prefetch** (chứng minh binary đã từng chạy) ⇒ máy đó **vẫn bị xâm nhập**. Đừng loại vì "không còn
  file".
- **.003 — máy sạch nhiều nhiễu:** phần mềm quản trị, agent backup tạo nhiều hoạt động giống tấn công
  nhưng khớp HV-40 whitelist ⇒ không đưa vào. Mỗi máy đưa vào phải có evidence ID chống lưng.
- F2 ⇒ ưu tiên không bỏ sót; nhưng mỗi máy sạch đưa vào vẫn làm giảm precision.

---

## T1103 — Phân tích các vụ xâm nhập (Cyber Kill Chain)

Phân tích **chuỗi hành vi bất thường và TTPs** thay vì chỉ IOC/signature; phân tích theo **Cyber Kill
Chain** để hiểu từng giai đoạn. Đầu ra: phân tích kỹ thuật từng giai đoạn.

| Subtask | Mode | Đầu vào | Phải nộp | Chấm |
|---|---|---|---|---|
| **T1103.001** | file | HV-02 (20 sự kiện bị xáo trộn) | `kill_chain_order[]` | Kendall τ |
| **T1103.002** | file | HV-02, HV-15 | `kill_chain_order[]`, `stage{}` | 0.6 τ + 0.4 enum |
| **T1103.003** | soc (EDR, SIEM, NSM) | HV-02 15 16 18 20 22 26 34 (trọn case đã khép, có ảnh bộ nhớ) | `vector`, `timeline[]`, `scope[]`, `malware_verdict` | 0.3 / 0.3 / 0.2 F2 / 0.2 |

- **Thứ tự Kill Chain** (Lockheed Martin): Reconnaissance → Weaponization → Delivery → Exploitation →
  Installation → Command & Control → Actions on Objectives. Dùng đúng nhãn giai đoạn trong `options`.
- **.001:** sắp theo **logic giai đoạn**, dùng timestamp làm phụ — nhưng sự kiện có thể bị xáo cả thời
  gian; quan hệ nhân quả (phải có delivery trước exploitation) thắng timestamp mơ hồ. Liệt kê **đủ 20
  ID**.
- **.002:** `stage{}` gán giai đoạn cho **từng** sự kiện (dict `event_id → stage`).
- **.003 — trọn case:** `vector` = đường vào ban đầu; `timeline[]` các mốc theo thời gian (điểm =
  0.5·τ + 0.5·recall mốc; **mốc lệch quá ±5 phút tính sai**); `scope[]` host bị ảnh hưởng (F2);
  `malware_verdict` từ HV-34 + ảnh bộ nhớ HV-20 (tiến trình inject, kết nối chỉ có trong RAM).
  Chuẩn hoá mọi mốc về UTC trước khi so (xem `soc-ir` T0173).

---

## T2013 — Tìm chỉ dấu của hoạt động xâm nhập

Chủ động tìm dấu hiệu xâm nhập trên **toàn bề mặt tấn công**: endpoint (máy chủ, máy trạm, thiết bị OT),
lưu lượng mạng, email, log Firewall/Proxy/SIEM. Khuyến nghị tối thiểu 6 tháng/lần, 3 tháng/lần với hệ
thống quan trọng.

| Subtask | Mode | Đầu vào | Phải nộp | Chấm |
|---|---|---|---|---|
| **T2013.001** | file | HV-02 log thô | `ioc{}` | **F1 macro theo 6 loại IOC** |
| **T2013.002** | file | HV-02, HV-16 | `ioc{}`, `antiforensics[]` `{kind, location}` | 0.6 / 0.4 |
| **T2013.003** | soc (EDR, SIEM) | HV-02 15 16 18 26 40 (đa nguồn, trọn đợt săn) | `ioc{}`, `antiforensics[]`, `timeline[]` | 0.5 / 0.3 / 0.2 |

**Trích IOC — gold pilot T2013.001:** `{"ioc": {"ipv4": [], "domain": [], "url": [], "sha256": [],
"email": [], "cve": []}}`. Refang (`hxxp`, `[.]`), chữ thường, bỏ IP private (10/8, 172.16/12,
192.168/16, 127/8) và domain lành tính/của tổ chức (`example.com`, mail domain nội bộ), không đưa host
của URL hay domain của email vào `domain`, không coi tên file (`gate.php`) là domain. Chi tiết:
`.claude/skills/soc-cnt/reference/coverage-intel.md`.

**Dấu vết chống điều tra (.002/.003)** — `{kind, location}`, location là path/kênh log:

| Kiểu | Dấu hiệu |
|---|---|
| xoá event log | Security **1102** (audit log cleared), System 104; khoảng trống log đúng lúc tấn công |
| vô hiệu hoá EDR/AV | service EDR dừng/đổi startup type, exclusion lạ, driver EDR bị gỡ (HV-14 ngừng gửi) |
| sửa timestamp (timestomping) | mtime/ctime **lùi** trước thời điểm tạo hợp lý, lệch giữa các nguồn thời gian |
| xoá lịch sử/shadow copy | `.bash_history` bị xoá/`HISTFILE=/dev/null`, `vssadmin delete shadows` |

Đề cấy sẵn: **log 1102 bị xoá, EDR bị tắt, timestamp bị sửa lùi**. Bản thân hành vi chống điều tra là
chỉ dấu mạnh — báo cả khi không còn payload.

---

## T2016 — Xác định các khu vực đã bị xâm phạm

Xác định toàn bộ khu vực bị xâm phạm: máy trạm, máy chủ, tài khoản người dùng đã bị chiếm quyền hoặc bị
ảnh hưởng. Đầu ra: **bản đồ phạm vi bị xâm phạm**.

| Subtask | Mode | Đầu vào | Phải nộp | Chấm |
|---|---|---|---|---|
| **T2016.001** | file | HV-26 | `accounts[]` | F2 |
| **T2016.002** | file | HV-26, HV-27 | `hosts[]`, `accounts[]` | 0.5 F2 + 0.5 F2 |
| **T2016.003** | soc (SIEM, EDR, NSM) | HV-04 14 15 16 17 18 22 26 27 33 37 38 | `hosts[]`, `accounts[]`, `level{}` | Σ − **0.5 × số phần tử xếp sai mức** |

- **Tài khoản bị chiếm (.001):** đăng nhập thành công bất thường — sau chuỗi thất bại (brute
  force/spray), từ nguồn/giờ/máy lạ, logon type lạ với tài khoản đó, dùng để lateral; tài khoản mới do
  attacker tạo. Account chuẩn hoá bỏ `DOMAIN\`/`@domain`.
- **Máy bị xâm phạm (.002):** thêm log biên (HV-27): máy có kết nối C2/VPN lạ/proxy bất thường, máy là
  đích của tài khoản bị chiếm.
- **.003 — ba mức** (dùng đúng nhãn của đề):
  - `bị_kiểm_soát` — attacker **thực thi được** trên máy/dùng được tài khoản: phiên đăng nhập thành công
    + thực thi, C2 từ máy, persistence được cài.
  - `bị_chạm` — attacker **có tương tác** nhưng chưa thấy kiểm soát: truy cập share/file, kết nối tới
    được nhưng không thấy thực thi.
  - `chỉ_bị_dò` — chỉ bị quét/thử, không truy cập thành công (port scan, đăng nhập thất bại).
  - Hai mức đầu dẫn tới **hai kế hoạch xử lý khác hẳn** (dựng lại máy/đổi mật khẩu vs điều tra thêm).
  - **Mỗi phần tử xếp sai mức trừ 0.5** — gán mức dựa trên bằng chứng cụ thể; không chắc thì chọn mức
    mà bằng chứng chứng minh được (thấp hơn), không "đôn" lên.

## Bẫy hay gặp

- Bỏ máy chỉ còn dấu vết quá khứ vì "không thấy file độc".
- Đưa máy quản trị/backup nhiều nhiễu vào danh sách xâm nhập.
- Sắp Kill Chain thuần theo timestamp khi timestamp bị xáo/sửa.
- Đếm một domain hai lần (url + domain), đưa IP private vào IOC.
- Gán `bị_kiểm_soát` cho máy chỉ bị quét.
