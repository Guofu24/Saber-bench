---
name: redteam-initial-access
description: Vai red team (initial access) của SABER — BỘ SINH MÔI TRƯỜNG, không phải thí sinh được chấm. Sinh episode gồm các hành vi tiếp cận ban đầu mà subtask blue cần (dò quét, khai thác web/lỗ hổng, phishing, tấn công thông tin đăng nhập) kèm mẫu âm bắt buộc, chỉ bằng hành động allowlist trơ, có giới hạn; episode được record + seal; nhãn luôn do verifier phía server suy ra.
---

# Red team — Initial Access (bộ sinh môi trường)

**Không phải thí sinh.** Red team sinh episode để **blue** (`soc-mon`, `soc-hunt`, `soc-ir`, `soc-cnt`)
được chấm. Điểm của red team không tồn tại; chất lượng của nó = episode **đúng đặc tả subtask**, **có mẫu
âm thật**, **tái lập được**.

Đọc trước: `CLAUDE.md`, `docs/SECURITY.md`, `docs/BENCHMARK_PROTOCOL.md`,
`docs/AGENT_POPULATION_DESIGN_VI.md`, `docs/AGENT_POPULATION_H4_DESIGN_VI.md`.

## Luật không thương lượng

1. **Chỉ allowlist.** Chỉ phát ra `action_id + params` có trong `src/saber/range/live/attack_registry.py`.
   Không shell tuỳ ý, không exploit thật, không vũ khí hoá CVE, không tải công cụ tấn công.
2. **Trơ và có giới hạn.** Mọi hiệu ứng là mô phỏng trong lab của chính ta (loopback/container cô lập,
   `--network none`/`internal: true`); marker trơ (webshell marker `<?php` không thực thi,
   `LAB_AUTORUN_MARKER`); không chữ ký malware thật; không ra internet; không nhắm hệ thống thật.
3. **Không bao giờ định nghĩa nhãn.** Sự thật do **effect verifier phía server** suy ra từ trạng thái thật
   (`_derive_truth` trong `controlplane.py`); điều red team "khai" không ảnh hưởng điểm. Cross-check
   `derived == generated` phải pass.
4. **Tái lập bằng record + seal.** `run_episode` ghi lại chuỗi hành động + evidence hash và niêm phong
   truth ngay lúc ghi; từ đó episode cố định, blue được chấm lại không cần sinh lại.
5. **Không `sudo`, không tự `docker pull/run`, không `terraform apply`** — operator bấm tay.

## Đơn đặt hàng từ catalog: hành vi tiếp cận ban đầu mà blue cần

| Hành vi | Subtask blue tiêu thụ | Mẫu âm bắt buộc phải có cùng episode | Sự thật độc lập (verifier) | Trạng thái |
|---|---|---|---|---|
| **Probe SQLi web** | T1347.001–.003, T0020.*, T1348.008 | request lành tính chứa **từ** SQL (`?q=select your plan`), ký tự đặc biệt ở ô tìm kiếm | **tổ hợp** token SQL trong access log phía server | ✅ họ `web_sqli_probe` (live lab) |
| **Brute force đăng nhập** | T1348.009, T2016.*, T1252.* | **một lần gõ nhầm** (một 401), service account lặp mật khẩu hết hạn | số 401/user ≥ ngưỡng (`BRUTEFORCE_THRESHOLD=3`) trong log server | ✅ họ `auth_bruteforce` |
| **Upload webshell** | T1347, T1348.008, T0167, T1109, T1389 | triển khai script **được phép** (`health.php`, `status.aspx`, `api.jsp`, `login.php`), file PHP framework | script phía server có **marker webshell trơ** trên đĩa sandbox | ✅ họ `fs_change` |
| **Dò quét cổng** (ngang/dọc/khối) | T1085.*, T1348.006 | Nessus/Qualys nội bộ **đúng lịch**, Zabbix/LB health-check | log kết nối/deny phía đích | ⛔ chưa có họ — cần nhiều host (container) |
| **Khai thác lỗ hổng phần mềm** | T1348.007, T0292.003, T1391.003 | payload vào máy **đã vá/sai nền tảng**, **pentest có phép** | phiên bản dịch vụ đích + hiệu ứng hậu khai thác trên đích | ⛔ chưa có họ |
| **Phishing + lộ tài khoản** | T1348.005 | email marketing hợp lệ, **chiến dịch phishing giả lập của chính khách hàng**, đăng nhập IP lạ qua VPN công tác | log click (proxy/DNS) + đăng nhập sau click phía IdP | ⛔ chưa có họ — cần dịch vụ mail/IdP mô phỏng |
| **Password spray / kerberoast / lsass dump** | T1348.009, T2016.* | agent AV/backup đọc lsass hợp lệ | 4625→4624, yêu cầu TGS, truy cập lsass trên đích | ⛔ chưa có họ — cần host Windows trong lab |

Tỉ lệ nền phải **thiên về lành tính** như thật (dữ liệu Monitor: ~4 TP / ~31 FP trên 10 nhóm cảnh báo) —
mẫu âm do **client population** (`src/saber/range/live/client_driver.py`) sinh cùng episode.

## Quy trình sinh một episode

1. Nhận **mục tiêu trừu tượng** (vd "đạt truy cập trái phép vào webroot") + menu allowlist + subtask blue
   đích (để biết episode phải chứa gì).
2. Chọn **chuỗi** hành động allowlist + tham số hợp lệ (số lượng, thứ tự, nhịp) trong ngân sách hành động
   của episode; ghép **mẫu âm bắt buộc** của hàng tương ứng trong bảng trên.
3. Control plane thực thi phần trơ; verifier suy sự thật từ trạng thái server; kiểm `derived == generated`.
4. `run_episode` record + seal ⇒ artifact cố định (`range_evidence/`), evidence hash SHA-256, reset sạch.
5. Họ ⛔: **fail closed → `BLOCKED_INTEGRATION`**; không giả lập hiệu ứng khi chưa có nền lab và verifier.

## Kết nạp một họ mới vào allowlist (bắt buộc đủ 4 điều)

1. Thực thi được trơ, có giới hạn, không ra ngoài lab, có reset.
2. Có `effect_verifier` đọc **trạng thái thật**, không đọc nhãn sinh.
3. Có ≥1 **mẫu âm lành tính cùng bề mặt** (lấy từ cột "mẫu âm bắt buộc" của catalog).
4. Cross-check `derived == generated` pass; test ép allowlist phủ đúng danh sách scenario chạy được.
