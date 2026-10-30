---
name: soc-ir
description: Nghiệp vụ IR — Xử lý sự cố ATTT của SABER (DFIR). Tiếp nhận, triage tại t0, điều phối, xác định phạm vi; xử lý và thu thập chứng cứ theo order of volatility không làm đổi hash; phân tích registry, bộ nhớ (inject/fileless), lưu lượng mạng/PCAP (C2, exfil), phân tích mã độc cấp 1–3 và dịch ngược; dựng timeline UTC, Patient Zero và bản đồ lây nhiễm; quy kết nhóm tấn công thận trọng; chặn IOC đúng lớp, diệt trừ và khôi phục mà dịch vụ vẫn sống; kế hoạch khắc phục; báo cáo Executive/Technical và Incident Report có trích dẫn. Phủ 21 NICE task / 63 subtask.
---

# IR — Xử lý sự cố ATTT (DFIR)

**Đọc trước:** `.claude/skills/saber-episode-contract/SKILL.md` (nộp bài, chuẩn hoá, trích dẫn, gate
cap/penalty, mode vm với `actions`).

## Sứ mệnh và SLA (nguồn: `catalog/services.json`)

Điều tra bằng chứng số chuyên sâu: **correlation log đa nguồn**, endpoint artifact, **malware analysis
static/dynamic**, webshell, **timeline**, **root cause**, **scope of compromise**, **containment**,
**eradication**, **báo cáo**.

- Phản hồi **Critical ≤ 15 phút**, **High ≤ 30 phút**.
- Kích hoạt điều tra (bắt đầu thu thập & phân tích sơ bộ) **≤ 10 phút sau khi xác nhận phạm vi**.
- Báo cáo sơ bộ **≤ 24h**; báo cáo chính thức **≤ 24h sau khi xong phân tích + peer review**.
- Kết luận **phải dựa trên bằng chứng kỹ thuật** và được kiểm chứng nội bộ trước khi phát hành.

## Vòng đời xử lý sự cố (theo NIST SP 800-61) và task tương ứng

```
1. Tiếp nhận & điều phối ........ T0510 điều phối · T1250 triage tại t0 · T1252 phạm vi/khẩn cấp/tác động
2. Thu thập & xử lý chứng cứ .... T1324 order of volatility · T1370 thu dấu vết (vm) · T1607 khôi phục từ nguồn pháp y
3. Phân tích artifact ........... T0397 registry · T1253 bộ nhớ · T1323 lưu lượng mạng · T0182 mã độc / dịch ngược
4. Tái dựng & quy kết ........... T0173 timeline · T1391 Patient Zero + bản đồ lây nhiễm · T1090 truy tìm thủ phạm
5. Ngăn chặn, diệt trừ, khôi phục T1371 chặn IOC · T1109 xử lý dứt điểm (vm) · T1251 kế hoạch khắc phục · T1257 gia cố hệ thống
6. Theo dõi & báo cáo ........... T1315 theo dõi SLA · T1316 hồ sơ sự cố · T1617 Executive/Technical · T1332 Incident Report
```

## Bản đồ task → tài liệu tham chiếu

| NICE | Việc | Mode các subtask | Đọc |
|---|---|---|---|
| T0510 | Điều phối chức năng ứng cứu sự cố | file, file, soc | `reference/triage-coordination.md` |
| T1250 | Phân loại ưu tiên sự cố (triage) | file, file, soc | `reference/triage-coordination.md` |
| T1252 | Phạm vi, mức khẩn cấp, tác động | file, file, soc | `reference/triage-coordination.md` |
| T1315 | Theo dõi sự cố đến khi xử lý xong | file, file, soc | `reference/triage-coordination.md` |
| T1316 | Ghi nhận sự cố đến khi xử lý xong | file, file, soc | `reference/triage-coordination.md` |
| T1324 | Xử lý chứng cứ số | file×3 | `reference/evidence-forensics.md` |
| T1370 | Thu thập dấu vết xâm nhập | vm×3 | `reference/evidence-forensics.md` |
| T1607 | Khôi phục thông tin từ nguồn pháp y | file, file, soc | `reference/evidence-forensics.md` |
| T0397 | Phân tích Windows registry | file, file, vm | `reference/evidence-forensics.md` |
| T1253 | Phân tích động (bộ nhớ) | file×3 | `reference/evidence-forensics.md` |
| T0182 | Phân tích malware cấp 1, 2, 3 (tĩnh, động, dịch ngược) | file×3 | `reference/malware-analysis.md` |
| T1323 | Phân tích lưu lượng mạng độc hại | file, file, soc | `reference/network-attribution.md` |
| T1090 | Truy tìm thủ phạm (quy kết APT) | file×3 | `reference/network-attribution.md` |
| T0173 | Phân tích dòng thời gian | file, file, soc | `reference/reconstruction.md` |
| T1391 | Tái dựng cuộc tấn công | file, file, soc | `reference/reconstruction.md` |
| T1371 | Giảm thiểu sự cố (chặn IOC) | file, file, soc | `reference/containment-eradication.md` |
| T1109 | Xử lý dứt điểm sự cố (eradication & recovery) | vm×3 | `reference/containment-eradication.md` |
| T1251 | Khuyến nghị chiến lược khắc phục | file×3 | `reference/containment-eradication.md` |
| T1257 | Khuyến nghị giảm thiểu & khắc phục cho doanh nghiệp | file×3 | `reference/containment-eradication.md` |
| T1617 | Chuẩn bị báo cáo phòng thủ mạng | file×3 | `reference/reporting.md` |
| T1332 | Lập báo cáo kết quả điều tra | file×3 | `reference/reporting.md` |

## Nguyên tắc nghề

1. **Bảo toàn chứng cứ trước, phân tích sau.** Thu theo order of volatility (RAM → kết nối → tiến trình
   → disk → log tập trung), hash từng tệp, biên bản, chuỗi bàn giao; thu ảnh bộ nhớ **trước** khi cô lập.
2. **Chỉ dùng dữ kiện có tại thời điểm được hỏi.** Triage (T1250) chỉ có dữ kiện ở t0 — không dùng kết
   luận về sau.
3. **Không quan sát được ≠ không xảy ra.** Khoảng log bị xoá là `khong_du_du_kien`; exfil có thể là
   `có_nguy_cơ` ("không loại trừ" là kết luận IR hợp lệ); quy kết không đủ căn cứ là
   `khong_du_can_cu_quy_ket`.
4. **Timestamp sớm nhất chưa chắc là Patient Zero** — đề cấy máy có dấu vết sớm hơn do quét lỗ hổng hợp lệ.
5. **Diệt trừ triệt để nhưng không phá dịch vụ.** Gỡ mọi backdoor/kênh tự phục hồi/tài khoản giả, giữ
   file sạch, khôi phục cấu hình, dịch vụ web phải còn phục vụ được.
6. **Chặn đúng đích, đúng lớp.** Không chặn CDN dùng chung, không chặn IP của chính hệ thống giám sát,
   không chặn dải CIDR rộng.
7. **Mọi kết luận có trích dẫn; mọi con số nhất quán** giữa Executive và Technical.

## Ràng buộc thao tác

- Hành động phản ứng (chặn, cô lập, xoá) chỉ **khai báo** và chỉ áp lên lab/snapshot; trên hệ thống thật
  cần lab cô lập + phê duyệt riêng (`docs/SECURITY.md`). Live lab của SABER có quarantine **có phê duyệt
  một lần, gắn đích, đảo ngược được, verify từ filesystem thật** (`src/saber/range/live/ir_actions.py`).
- Dịch ngược chỉ trên **mẫu lành tính tự build** khi có Docker + image Ghidra pin digest, `--network
  none`, read-only; không tự kéo mã độc thật (xem `reference/malware-analysis.md`).

## Trạng thái chấm (trung thực)

63 subtask `VERIFIED_OFFLINE`; 10 `soc` + 7 `vm` cần SIEM/EDR/NSM/VM thật ⇒ `BLOCKED_INTEGRATION` ở mức
hệ thống. Exemplar viết tay: T0173.001, T0397.002, T1109.003. Gold pilot: T0173.002, T0397.002,
T1324.002. Live lab chấm IR thật trên họ `fs_change` (quarantine webshell, đo containment recall và
**false containment**). 0 `READY_BENCHMARK`.
