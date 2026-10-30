---
name: soc-mon
description: Nghiệp vụ MON — Vận hành giám sát ATTT 24/7 (SOC Tier 1/2, alert-based) của SABER. Kiểm chứng cảnh báo TP/FP, phân biệt lành tính/độc hại theo 10 nhóm cảnh báo, xác định nguyên nhân và tác động, ghi ticket, leo thang, thông báo theo RASCI/SLA, cô lập/gỡ mã độc khi được cấp quyền, giám sát liên tục và báo cáo tháng. Phủ 16 NICE task / 58 subtask (T1085 T1112 T1241 T1242 T1290 T1299 T1347 T1348 T1349 T1350 T1351 T1386 T1387 T1388 T1389 T1428).
---

# MON — Vận hành giám sát ATTT 24/7

**Đọc trước:** `.claude/skills/saber-episode-contract/SKILL.md` (cách đọc episode, nộp bài, chuẩn hoá,
trích dẫn, gate). Skill này chỉ nói *làm nghiệp vụ thế nào cho đúng*.

## Sứ mệnh và SLA (nguồn: `catalog/services.json`)

Phân tích, điều tra cảnh báo theo cơ chế **alert-based**: có cảnh báo thì chuyên gia mới phân tích; gán
cảnh báo vào case hoặc đóng **False Positive**; phản ứng nhanh (containment) **khi được cấp quyền
trước**; vận hành ticket theo SLA.

- Cảnh báo **Nghiêm trọng/Cao ≤ 30 phút**, **Trung bình ≤ 1 giờ**; sự cố có hướng dẫn ≤ 24/72 giờ.
- Mục tiêu đúng hạn ≥ 90%; **bỏ lọt sự cố Nghiêm trọng/Cao = 0**.
- FP không tính vào SLA sự cố nhưng **vẫn tính vào SLA xử lý cảnh báo**.

## Dòng việc của một ca trực (thứ tự nghiệp vụ thật)

```
cảnh báo đến ─► (1) kiểm chứng TP/FP ─► (2) nguyên nhân & cơ chế ─► (3) tác động & severity
                    T1112 T1387 T1348        T1299 T1347 T1386 T1085      T1351
      ─► (4) ghi ticket ─► (5) leo thang ─► (6) thông báo ─► (7) phản ứng nhanh (nếu được cấp quyền)
            T1241            T1242            T1349 T1428       T1388 cô lập · T1389 gỡ bỏ
      song song: giám sát liên tục & hàng đợi T1350 · báo cáo tháng T1290
```

Ba câu hỏi Tier 1 phải trả lời cho **mọi** cảnh báo: *Đúng hay sai? Cái gì gây ra, trên tài sản nào?
Nặng tới đâu, ai phải biết, trong bao lâu?*

## Bản đồ task → tài liệu tham chiếu

| NICE | Việc | Subtask | Mode | Đọc |
|---|---|---|---|---|
| T1112 | Kiểm chứng cảnh báo mạng | .001–.003 | file, file, soc | `reference/alert-validation.md` |
| T1387 | Thẩm định cảnh báo IDS | .001–.003 | file, file, soc | `reference/alert-validation.md` |
| T1348 | Lành tính vs độc hại (13 bài, 10 nhóm cảnh báo) | .001–.013 | file×2, soc×11 | `reference/alert-groups.md` |
| T1299 | Nguyên nhân của cảnh báo | .001–.003 | file, file, soc | `reference/cause-impact.md` |
| T1351 | Tác động tới hệ thống & thông tin | .001–.003 | file, file, soc | `reference/cause-impact.md` |
| T1347 | Phát hiện tấn công/xâm nhập | .001–.003 | file, file, soc | `reference/detection.md` |
| T1386 | Bất thường lưu lượng mạng (C2, tunnel) | .001–.003 | file, file, soc | `reference/detection.md` |
| T1085 | Mối đe doạ tới tài nguyên mạng | .001–.003 | file, file, soc | `reference/detection.md` |
| T1241 | Ghi nhận sự cố (ticket) | .001–.003 | file, file, soc | `reference/case-lifecycle.md` |
| T1242 | Leo thang sự cố | .001–.003 | file, file, soc | `reference/case-lifecycle.md` |
| T1349 | Truyền đạt cảnh báo tấn công | .001–.003 | file, file, soc | `reference/case-lifecycle.md` |
| T1428 | Thông báo quản lý / IR / nhà cung cấp | .001–.003 | file, file, soc | `reference/case-lifecycle.md` |
| T1350 | Giám sát liên tục | .001–.003 | file, file, soc | `reference/case-lifecycle.md` |
| T1290 | Báo cáo sự kiện/hoạt động định kỳ | .001–.003 | file, file, soc | `reference/case-lifecycle.md` |
| T1388 | Cô lập malware | .001–.003 | file, file, soc | `reference/containment.md` |
| T1389 | Loại bỏ malware | .001–.003 | vm×3 | `reference/containment.md` |

Quy luật độ khó trong catalog: `.001` = một hiện vật, một quyết định; `.002` = thêm ngữ cảnh (log thô,
whitelist, ma trận) và một trường phải *suy ra*; `.003` = trọn case đa nguồn, thường có **gate CITE**
hoặc ràng buộc cứng. Làm `.003` như ca thật: đủ bằng chứng, đủ trích dẫn.

## Hiện vật MON hay dùng (HV)

HV-01 cảnh báo gốc · HV-02 log thô ±60′ · HV-04 danh mục & sức khoẻ log source · HV-06 thống kê alert
theo rule · HV-07 case + phán quyết · HV-08 worklog · HV-10 vòng đời case & SLA · HV-12 ticket lỗ hổng ·
HV-14 detection EDR · HV-15 telemetry tiến trình · HV-17 netconn endpoint · HV-21 cảnh báo NSM/IDS ·
HV-22 flow · HV-23 DNS/HTTP/TLS · HV-24 PCAP · HV-26 AD/Windows · HV-27 Firewall/Proxy/VPN · HV-28 web &
WAF · HV-29 email · HV-30 cloud · HV-31 ứng dụng & CSDL · HV-37 sơ đồ mạng · **HV-38 danh mục tài sản**
(tier, VIP, cấp độ hệ thống) · **HV-39 ma trận severity & SOP** (RASCI, kênh, SLA) · **HV-40 whitelist**.

## Nguyên tắc nghề (áp cho mọi bài MON)

1. **Không tin tên rule/tên phát hiện AV.** Tên rule có thể sai nhóm (vd rule `NSM_PORT_SCAN` gắn vào
   cảnh báo về interpreter beacon). Kiểm chứng *claim* của cảnh báo bằng log và telemetry.
2. **Whitelist và danh mục tài sản là bằng chứng, không phải tham khảo.** Hầu hết FP trong đề là hoạt
   động quản trị hợp lệ: change ticket, admin subnet, chữ ký tin cậy, scanner theo lịch, jump host/PAM.
3. **Ngữ cảnh quyết định severity.** CVSS cao không phơi ra ngoài có thể chỉ Thấp; máy VIP và hệ thống
   cấp độ 3 (Nghị định 85/2016/NĐ-CP) đẩy severity lên.
4. **Không đủ dữ liệu thì nói không đủ dữ liệu** (`INCONCLUSIVE`, `unverified`) — đừng ép TP/FP.
5. **Mọi khẳng định ở mức `.003` phải trích được** bằng evidence ID có thật.
6. **Phản ứng chỉ khi được cấp quyền** và chỉ trong lab: không bao giờ cô lập máy VIP, không chặn dải
   chứa hệ thống cấp 3, thu ảnh bộ nhớ **trước** khi cô lập.

## Trạng thái chấm (trung thực)

Toàn bộ 58 subtask là `VERIFIED_OFFLINE` trên fixture DEV; bài `soc` (25) và `vm` (3) còn
`BLOCKED_INTEGRATION` với SIEM/SOAR/EDR/VM thật. Exemplar viết tay có dữ liệu nghiệp vụ:
T1112.001–.003, T1348.001, T1290.001. Live lab chấm thật `T1347.001` (set_delta) trên telemetry
loopback. 0 `READY_BENCHMARK`.
