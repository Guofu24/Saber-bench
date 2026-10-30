---
name: soc-hunt
description: Nghiệp vụ HUNT — Threat Hunt / Compromise Assessment của SABER. Săn tìm chủ động trên endpoint và mạng (file/hash/webshell, persistence, tiến trình, kết nối C2/tunnel), quét thiết bị không để lại dấu vết, phát hiện và phân tích xâm nhập theo Kill Chain, trích IOC và dấu vết chống điều tra, xác định phạm vi bị xâm phạm, ánh xạ ATT&CK, rà cấu hình không an toàn và ưu tiên vá lỗ hổng, lập Technical Report. Phủ 13 NICE task / 39 subtask (T0292 T0167 T1102 T1103 T1104 T1381 T1487 T0845 T1053 T1341 T2012 T2013 T2016).
---

# HUNT — Threat Hunt · Compromise Assessment

**Đọc trước:** `.claude/skills/saber-episode-contract/SKILL.md` (nộp bài, chuẩn hoá host/account/IOC,
trích dẫn, gate `machine_unchanged`).

## Sứ mệnh và chu kỳ (nguồn: `catalog/services.json`)

Săn tìm **chủ động** trên endpoint bằng Viettel Scanner + IOC/pattern mới nhất: tiến trình, persistence,
RAM, file thực thi, **source code webshell**, kết nối outbound C2. Mở rộng sang **rà soát chuyên sâu**
(Compromise Assessment): anti-forensics, log AV xử lý thất bại, cấu hình không an toàn, lateral movement
qua remote service, dựng **Patient Zero + bản đồ lây nhiễm + timeline**, **Threat Removal Plan**.

- Săn tìm: khuyến nghị **6 tháng/lần** toàn hệ thống, **3 tháng/lần** với hệ thống quan trọng.
- Rà soát chuyên sâu: **12 tháng/lần** toàn hệ thống, **6 tháng/lần** với hệ thống quan trọng.
- **Chuyển sang IR ngay khi phát hiện tấn công** — hunter không tự xử lý sự cố.

Khác MON: MON *phản ứng* với cảnh báo; HUNT *giả định đã bị xâm nhập* và đi tìm thứ chưa có cảnh báo,
kể cả dấu vết **chỉ còn trong quá khứ** (file đã xoá, chỉ còn log AV/prefetch).

## Dòng việc một đợt săn tìm / CA

```
giả thuyết (TI, TTP, IOC mới) ─► thu thập quan sát (không sửa máy) ─► phát hiện ─► phân tích ─► phạm vi ─► báo cáo
                                   T1381 quét · T1487 file/registry   T1102        T1103        T2016      T1104
                                   T2012 kết nối · T0167 chữ ký tệp   T2013 IOC    T0845 ATT&CK
                                   T1341 cấu hình · T0292 lỗ hổng      + chống điều tra  T1053 chân dung
```

## Bản đồ task → tài liệu tham chiếu

| NICE | Việc | Subtask | Mode | Đọc |
|---|---|---|---|---|
| T0167 | Phân tích chữ ký tệp (hash, webshell, obfuscation) | .001–.003 | file×3 | `reference/file-malware-hunt.md` |
| T1381 | Quét virus trên vật chứa dữ liệu | .001–.003 | file, vm, vm | `reference/file-malware-hunt.md` |
| T1487 | Giám sát tệp & registry trên hệ thống đang chạy | .001–.003 | vm×3 | `reference/file-malware-hunt.md` |
| T1102 | Phát hiện các vụ xâm nhập | .001–.003 | file, file, vm | `reference/intrusion-analysis.md` |
| T1103 | Phân tích các vụ xâm nhập (Kill Chain) | .001–.003 | file, file, soc | `reference/intrusion-analysis.md` |
| T2013 | Tìm chỉ dấu xâm nhập (IOC, anti-forensics) | .001–.003 | file, file, soc | `reference/intrusion-analysis.md` |
| T2016 | Xác định khu vực bị xâm phạm | .001–.003 | file, file, soc | `reference/intrusion-analysis.md` |
| T0845 | Nhận diện chiến thuật & phương thức (ATT&CK) | .001–.003 | file, file, soc | `reference/ttp-actor.md` |
| T1053 | Mô tả hoạt động xâm nhập nhằm vào nạn nhân | .001–.003 | file, file, soc | `reference/ttp-actor.md` |
| T2012 | Kiểm tra kết nối mạng | .001–.003 | file, file, vm | `reference/exposure-review.md` |
| T1341 | Rà soát theo yêu cầu (cấu hình không an toàn) | .001–.003 | file, file, vm | `reference/exposure-review.md` |
| T0292 | Khuyến nghị khắc phục lỗ hổng | .001–.003 | file, file, soc | `reference/exposure-review.md` |
| T1104 | Ghi nhận những gì đã biết (Technical Report) | .001–.003 | file×3 | `reference/reporting.md` |

## Nguyên tắc nghề

1. **Quan sát, không đụng.** Bài vm của HUNT (T1381.002/.003, T1487.*, T1341.003, T2012.003, T1102.003)
   đều **cấm sửa máy**: verifier so SHA-256 trước/sau. Chỉ khai báo `read`. Hunter không tự gỡ — gỡ là
   việc của IR (`soc-ir`) hoặc MON (T1389).
2. **Whitelist và danh mục tài sản quyết định precision.** Máy sạch "nhiều nhiễu" (phần mềm quản trị,
   agent backup, certbot/logrotate, template engine dùng `eval`) là mẫu âm bắt buộc trong nhiều bài.
3. **Dấu vết quá khứ cũng là xâm nhập.** File đã xoá nhưng còn log AV, prefetch, event log ⇒ máy đó vẫn
   bị xâm nhập (T1102.002).
4. **F2 cho phạm vi:** bỏ sót máy/tài khoản bị xâm phạm đắt hơn báo thừa — nhưng phân mức sai bị phạt
   (T2016.003).
5. **Không có bằng chứng thì không liệt kê** — technique, máy, tài khoản không trích được bị loại hoặc
   làm trượt gate CITE.
6. **Thấy tấn công đang diễn ra ⇒ chuyển IR**, ghi rõ trong báo cáo.

## Trạng thái chấm (trung thực)

39 subtask `VERIFIED_OFFLINE`; 6 `soc` + 8 `vm` cần EDR/SIEM/VM thật ⇒ `BLOCKED_INTEGRATION` ở mức hệ
thống (VM thật cần lab cô lập + snapshot). Exemplar viết tay: T0845.001, T1487.003, T2012.001. Gold
pilot: T0167.002, T1102.002, T2013.001. Live lab chưa có họ cho HUNT ngoài telemetry chung. 0
`READY_BENCHMARK`.
