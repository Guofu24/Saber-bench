# CNT · Độ phủ ATT&CK và tình báo thành rule — T1384 (intrusion set) · T1644 (chỉ dấu tác chiến)

---

## T1384 — Thiết lập quy trình về tập hành vi xâm nhập (intrusion set)

Săn tìm **theo giả thuyết**: từ một kỹ thuật tấn công mới trong MITRE ATT&CK, xây **Usecase Hunting** rồi
truy vấn event log xem hệ thống khách hàng có dấu vết tương tự không. Nôm na: từ hiểu biết về một nhóm
tấn công (kỹ thuật, tool, hạ tầng), xây các bước **lặp lại được** để nhận diện và truy vết đúng nhóm đó
mỗi khi nó xuất hiện. Đầu ra: bộ use-case hunting theo technique + kết quả kiểm chứng trên log thật.

| Subtask | Mode | Đầu vào | Phải nộp | Chấm |
|---|---|---|---|---|
| **T1384.001** | file | HV-05 kho rule + mapping ATT&CK, 1 technique | `covered` | enum 1.0 |
| **T1384.002** | file | HV-04, HV-05, cả intrusion set | `uncovered[]` technique chưa rule nào phủ | F1 (technique) |
| **T1384.003** | soc (SIEM, EDR) | HV-04 05 15 26 33 35 37 38 | `uncovered[]`, `hunt_query`, `insufficient_data` | 0.5 F1 + 0.5 exec + **gate** |

**Thế nào là "đã phủ"**
1. Có ≥1 rule **đang bật** trong HV-05 được map **đúng technique ID** đó (so đúng cấp: `T1059.001` khác
   `T1059`; không tự suy rule cấp cha phủ sub-technique trừ khi HV-05 ghi vậy).
2. **Và** nguồn log mà rule cần **tồn tại và khoẻ** trong HV-04. Rule tồn tại nhưng log source chưa
   on-board hoặc đang hỏng ⇒ trên thực tế **không phủ** — đây là lý do .002 cấp thêm HV-04.

**.002 — liệt kê technique chưa phủ:** duyệt từng technique của intrusion set, áp 2 điều kiện trên.
Technique chuẩn hoá `Txxxx(.xxx)`. F1 ⇒ không liệt kê thừa technique ngoài intrusion set.

**.003 — use-case hunting chạy được**
- `hunt_query`: truy vấn/rule chạy được trên corpus (engine regex ở DEV — `engines.md`) bắt dấu vết của
  technique; viết hẹp như rule phát hiện.
- **Bẫy cố ý:** một đề **thiếu hẳn nguồn log** cần cho technique ⇒ đáp án đúng là **"không đủ dữ liệu"**
  (`insufficient_data`), **không phải** "không có dấu vết". Kiểm HV-04 trước khi kết luận sạch: không
  quan sát được ≠ không xảy ra. Sai gate này nhân 0.
- Ghi kết quả vào báo cáo TH/CA (HV-33) và cập nhật mapping (HV-05) — ngoài đời, use-case mới đi vào kho
  rule có phiên bản.

---

## T1644 — Xây dựng chỉ dấu cho tác chiến mạng

Chuyển thông tin chiến dịch, lỗ hổng và IOC từ VCS Threat Intelligence thành **bộ rule giám sát khả thi**
(Content Security), **bộ chỉ dấu săn tìm** (Proactive Threat Hunting) và **chữ ký Yara/Sigma** (Threat
Hunting, Compromised Assessment). Đầu ra: chỉ dấu tác nghiệp dạng **rule chạy được trên SIEM khách hàng**.

| Subtask | Mode | Đầu vào | Phải nộp | Chấm |
|---|---|---|---|---|
| **T1644.001** | file | HV-35 báo cáo TI | `ioc{}` toàn bộ IOC | **F1 macro theo loại IOC** (chuẩn hoá defang, lowercase trước khi so) |
| **T1644.002** | file | HV-34, HV-35 | `ioc{}`, `durability{}` | 0.7 / 0.3 |
| **T1644.003** | soc (SIEM, EDR) | HV-04 05 15 16 18 33 34 35 | `ioc{}`, `rule` | 0.4 / **0.6** — nặng về rule vì chép bảng IOC là việc máy làm được |

**Trích IOC (.001) — quy ước của gold pilot (T2013.001, cùng chuẩn; chờ adjudication)**
- Dạng: `{"ioc": {"ipv4": [...], "domain": [...], "url": [...], "sha256": [...], "email": [...], "cve": [...]}}`
  (theo đúng schema đề; fixture DEV có thể dùng list).
- **Refang + chuẩn hoá:** `hxxp`→`http`, `[.]`/`(.)`→`.`, `[@]`→`@`; chữ thường; bỏ `/` và `.` cuối URL.
- **Loại khỏi IOC:** IP private (10/8, 172.16/12, 192.168/16, 127/8), domain lành tính/của chính tổ
  chức (example.com, mail domain nội bộ), tên file (`.exe .dll .php …`), đoạn path.
- **Không đếm trùng loại:** host của URL đã nằm trong `url` thì không đưa vào `domain`; domain của email
  cũng vậy. Mỗi giá trị thuộc đúng một loại.
- Macro-F1 theo loại ⇒ loại hiếm (cve, email) quan trọng ngang loại phổ biến (ip) — đừng bỏ sót.

**Phân loại độ bền (.002) — Pyramid of Pain**
- **hash** — đổi được tức thì (biên dịch lại, thêm byte) ⇒ độ bền thấp nhất.
- **IP/domain** — đổi được với chi phí hạ tầng thấp ⇒ độ bền thấp/trung bình.
- **TTP** (hành vi, chuỗi kỹ thuật, cấu trúc C2) — **khó đổi** ⇒ độ bền cao, giá trị phát hiện lâu dài.
- Dùng đúng nhãn trong `options`/đề (vd hash đổi được / domain đổi được / TTP khó đổi).

**IOC → rule chạy được (.003)**
1. Rule đáng giá nhất bám **TTP bền** (HV-34 hành vi, HV-15 tiến trình, HV-16 persistence) chứ không
   chỉ là danh sách hash/IP.
2. Kiểm log source cần cho rule có trong HV-04 (giống T1384) — rule chạy trên nguồn không tồn tại là vô
   dụng.
3. Viết theo `engines.md`; hẹp, parse được, không timeout.

## Bẫy hay gặp

- Coi rule tồn tại là đã phủ mà không kiểm log source.
- Kết luận "không có dấu vết" khi thực ra thiếu nguồn log.
- Đưa IP private, domain nội bộ, tên file vào IOC; đếm một domain ở cả `url` lẫn `domain`.
- Ở .003 chỉ nộp bảng IOC chép lại — 0.6 điểm nằm ở rule.
