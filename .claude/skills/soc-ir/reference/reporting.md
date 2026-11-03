# IR · Báo cáo sự cố

Mốc thời gian/schema cụ thể dưới áp dụng khi case/SOP yêu cầu; không tự coi là deadline phổ quát.

Kết luận **phải dựa trên bằng chứng kỹ thuật** và được **peer review nội bộ** trước khi phát hành. Báo cáo sơ bộ ≤ 24
giờ; báo cáo chính thức ≤ 24 giờ sau khi xong phân tích và peer review.

## Executive Report và Technical Report

Hai lớp báo cáo: **Executive Report** tóm lược rủi ro cho Ban lãnh đạo; **Technical Report** chuyên sâu cho đội ATTT,
kèm đầy đủ bằng chứng số, log và kết quả phân tích mẫu.

**Lỗi hay gặp thật:** hai bản nói **hai con số khác nhau** về cùng một sự cố (số máy bị ảnh hưởng, số tài khoản, thời
điểm phát hiện, dung lượng dữ liệu ra).

**Quy trình**
1. Lập **bảng số liệu gốc một lần** từ bằng chứng: số host, số tài khoản, số IOC, mốc phát hiện, thời gian ngăn chặn,
   bytes ra… — mỗi con số một **khoá** cố định.
2. Cả hai bản **đọc từ cùng bảng** — cùng khoá, cùng giá trị, cùng đơn vị. Bản Executive diễn đạt cho lãnh đạo nhưng
   **không được đổi giá trị** (không "khoảng 20 máy" khi bảng ghi 17).
3. **Mục bắt buộc** của từng bản:
   - Executive: tóm tắt sự cố · mức độ và tác động kinh doanh · phạm vi · trạng thái xử lý · rủi ro còn lại ·
     khuyến nghị/quyết định cần lãnh đạo.
   - Technical: timeline · root cause · scope · IOC · TTP/ATT&CK · phân tích mã độc · hành động xử lý · bằng chứng và
     phụ lục.
4. Trích dẫn bằng chứng cho các con số và khẳng định chính.

```json
{"facts": {"hosts_affected": 17, "accounts_compromised": 3, "detected_at": "2026-10-17T06:45:00Z"},
 "executive": {"summary": "…", "hosts_affected": 17, "accounts_compromised": 3, "residual_risk": "…"},
 "technical": {"timeline": ["…"], "root_cause": "…", "hosts_affected": 17, "accounts_compromised": 3},
 "sections": {"executive": ["summary", "impact", "scope", "status", "residual_risk", "recommendations"],
              "technical": ["timeline", "root_cause", "scope", "ioc", "ttp", "malware", "actions", "evidence"]},
 "citations": ["…"]}
```

## Incident Report (kết quả điều tra)

Báo cáo xử lý sự cố gồm **root cause**, **attack chain** và **impact**, có peer review trước khi phát hành.

- **Root cause** = nguyên nhân gốc *thật*: điểm vào + điểm yếu bị lợi dụng (khai thác lỗ hổng X trên dịch vụ phơi ra
  ngoài; phishing dẫn tới đánh cắp thông tin đăng nhập; mật khẩu yếu bị brute force). Không phải triệu chứng (cảnh báo
  đầu tiên), không phải hậu quả (dữ liệu bị mã hoá).
- **Attack chain** = các bước từ **điểm xâm nhập tới hành vi cuối**: initial access → execution → persistence →
  privilege escalation → lateral movement → collection/exfiltration/impact. Đủ bước, không thêm bước không có bằng chứng.
- **Impact** = tài sản, dữ liệu, dịch vụ bị ảnh hưởng — ưu tiên không bỏ sót.
- **Mọi khẳng định kèm trích dẫn** tìm lại được. Nếu gói bằng chứng chưa có kết luận, tự suy từ hiện vật, không suy từ
  tên case.

```json
{"root_cause": "khai thác CVE-2023-4966 trên VPN gateway",
 "attack_chain": ["initial_access", "execution", "persistence", "lateral_movement", "exfiltration"],
 "impact": ["vpn-gw", "srv-file-01", "dữ liệu phòng kế toán"],
 "citations": [{"artifact": "Log Firewall/Proxy/VPN", "locator": "LOG-…", "excerpt": "…"}]}
```

## Sai lầm thường gặp

- Executive làm tròn/đổi số so với Technical.
- Thiếu mục bắt buộc của một trong hai bản.
- Root cause là triệu chứng; attack chain có bước tưởng tượng.
- Trích dẫn không trỏ được về bản ghi.

Nguồn nghiệp vụ: NICE T1617, T1332 (catalog SABER).
