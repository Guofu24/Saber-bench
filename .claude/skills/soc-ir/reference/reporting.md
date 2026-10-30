# IR · Báo cáo — T1617 (Executive / Technical) · T1332 (Incident Findings Report)

Kết luận **phải dựa trên bằng chứng kỹ thuật** và được **peer review nội bộ** trước khi phát hành. SLA:
báo cáo sơ bộ ≤ 24h; báo cáo chính thức ≤ 24h sau khi xong phân tích + peer review.

---

## T1617 — Chuẩn bị các báo cáo phòng thủ mạng

Hai lớp báo cáo: **Executive Report** tóm lược rủi ro cho Ban lãnh đạo, và **Technical Report** chuyên
sâu cho đội ATTT kèm đầy đủ bằng chứng số, log và kết quả phân tích mẫu.

| Subtask | Mode | Đầu vào | Phải nộp | Chấm |
|---|---|---|---|---|
| **T1617.001** | file | HV-32 Technical Report | bản Executive tương ứng | tỉ lệ **con số khớp** (±0) với khoá cùng tên ở bản Technical |
| **T1617.002** | file | HV-32, HV-36 | + mục bắt buộc của từng bản | 0.6 nhất quán + 0.4 `sections[]` (recall) |
| **T1617.003** | file | HV-02 12 26 32 33 36 | **cả hai** bản `executive.json` + `technical.json` có khoá chung | 0.4 nhất quán + 0.3 `citations[]` + 0.3 `sections[]` |

**Lỗi hay gặp thật (lý do bài này tồn tại):** hai bản báo cáo nói **hai con số khác nhau** về cùng một sự
cố (số máy bị ảnh hưởng, số tài khoản, thời gian phát hiện, dung lượng dữ liệu ra).

**Quy trình**
1. Lập **bảng số liệu gốc một lần** từ bằng chứng: số host, số tài khoản, số IOC, mốc phát hiện, thời gian
   ngăn chặn, bytes ra… — mỗi số một **khoá** cố định.
2. Bản Technical và bản Executive **đều đọc từ cùng bảng đó** (cùng khoá, cùng giá trị, cùng đơn vị). Bản
   Executive được làm tròn/diễn đạt cho lãnh đạo **không được đổi giá trị** — dung sai ±0.
3. **Mục bắt buộc** (.002/.003) theo checklist trong input. Thường gặp:
   - Executive: tóm tắt sự cố · mức độ & tác động kinh doanh · phạm vi · trạng thái xử lý · rủi ro còn lại ·
     khuyến nghị/quyết định cần lãnh đạo.
   - Technical: timeline · root cause · scope · IOC · TTP/ATT&CK · phân tích mã độc · hành động xử lý ·
     bằng chứng/phụ lục.
4. `citations[]` (.003): evidence ID thật cho các con số/khẳng định chính.
5. Ở fixture DEV tự động, `number_consistency` là một trường số theo schema cấu trúc; ở bài thật verifier
   **tự tính** tỉ lệ khớp từ hai bản báo cáo bạn nộp.

---

## T1332 — Lập báo cáo kết quả điều tra sự cố (Incident Report)

Xây dựng Incident Report gồm **root cause**, **attack chain** và **impact**, có peer review nội bộ trước
khi phát hành.

| Subtask | Mode | Đầu vào | Phải nộp | Chấm |
|---|---|---|---|---|
| **T1332.001** | file | HV-36 gói bằng chứng (đã che kết luận) | `root_cause` | enum 1.0 |
| **T1332.002** | file | HV-02, HV-36 | `root_cause`, `attack_chain[]` | 0.6 / 0.4 (set/step) |
| **T1332.003** | file | HV-02 15 26 28 32 36 | `root_cause`, `attack_chain[]`, `impact{}`, `citations[]` | 0.5 / 0.15 / 0.15 (F2) / 0.2 |

- **`root_cause`** = nguyên nhân gốc *thật*: điểm vào + điểm yếu bị lợi dụng (vd khai thác lỗ hổng X trên
  dịch vụ phơi ra ngoài; phishing dẫn tới đánh cắp thông tin đăng nhập; mật khẩu yếu bị brute force). Không
  phải triệu chứng (cảnh báo đầu tiên) và không phải hậu quả (mã hoá dữ liệu). Chọn trong tập nhãn của đề.
- **`attack_chain[]`** = các bước từ **điểm xâm nhập tới hành vi cuối** (initial access → execution →
  persistence → privilege escalation → lateral movement → collection/exfil/impact), mỗi bước một nhãn
  bước theo đề; tập hợp nên đủ và không thêm bước không có bằng chứng.
- **`impact{}`** (.003, F2): tài sản/dữ liệu/dịch vụ bị ảnh hưởng — ưu tiên không bỏ sót.
- **Mọi khẳng định kèm trích dẫn** để verifier grep lại (đúng nguyên tắc "kết luận phải dựa trên bằng chứng
  kỹ thuật"). Gói bằng chứng đã **che kết luận** — tự suy từ hiện vật, không suy từ tên case.

## Bẫy hay gặp

- Executive làm tròn số khác với Technical (vd "khoảng 20 máy" vs 17).
- Thiếu mục bắt buộc của một trong hai bản.
- Root cause là triệu chứng; attack chain thêm bước tưởng tượng.
- Trích dẫn không trỏ được về bản ghi.
