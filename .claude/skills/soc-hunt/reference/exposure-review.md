# HUNT · Kết nối, cấu hình và lỗ hổng — T2012 (kết nối mạng) · T1341 (rà soát cấu hình) · T0292 (khắc phục lỗ hổng)

---

## T2012 — Kiểm tra các kết nối mạng

Kiểm kết nối mạng **hiện hành** trên máy đích để phát hiện **kênh ra ngoài bất thường** và **kênh
tunneling đang được duy trì**. (Nghiệp vụ thuộc nhóm Điều tra số; có thêm tag IR.)

| Subtask | Mode | Đầu vào | Phải nộp | Chấm |
|---|---|---|---|---|
| **T2012.001** | file | HV-17 output `netstat` N kết nối, M bất thường | `abnormal[]` `{ip, port}` | set_delta |
| **T2012.002** | file | HV-17, HV-40 | `abnormal[]` `{ip, port, process}` | F1, **sai tiến trình = 0.5 phần tử** |
| **T2012.003** | vm | HV-15 17 22 23 24 27 40 — K = 25 kết nối, M = 4 C2/tunnel | `observations{abnormal}`, `actions` chỉ `read` | F1 × **[máy không đổi]** |

- **Phần tử = đầu xa của kết nối**: `ip` = remote IP, `port` = remote port (exemplar T2012.001).
- **Bất thường** (exemplar): kết nối **ra địa chỉ ngoài**, trên **cổng lạ** (4444, 1337, 6667, 9001,
  8081, 53413…), từ **tiến trình không nên mở socket ra ngoài**. **Lành tính**: lưu lượng nội bộ RFC1918,
  endpoint SaaS/cập nhật đã biết trên 80/443, dịch vụ hạ tầng (53, 123, 389, 445).
- **.002 — tiến trình:** "không biết tiến trình thì không chặn đúng chỗ". Ghép kết nối với PID/tên tiến
  trình; loại kết nối khớp HV-40 whitelist (đúng tiến trình + đúng đích).
- **.003 — máy đang chạy:** 4 kênh C2/tunnel kiểu **reverse shell**, **DNS tunnel**, **`ssh -R`**. Agent
  tự quan sát (ở offline: đọc snapshot `ss`/`lsof` có trong input), **không được sửa máy**. Dấu hiệu:
  shell (`bash`, `sh`, `nc`) có socket ra ngoài; `ssh` với remote forward tới host ngoài; tiến trình lạ gửi
  nhiều truy vấn DNS dài tới một domain (đối chiếu HV-23); flow ra đều đặn (HV-22).

---

## T1341 — Thực hiện các cuộc rà soát theo yêu cầu (Compromise Assessment)

Rà soát nguy cơ bảo mật có thể bị lợi dụng để xâm nhập: **cấu hình không an toàn** và điểm yếu như
**KeyWDigest**, **AccessibilityFeatures**, **IIS Machine Key** đã công bố bị lộ. Đầu ra: danh mục cấu
hình sai và điểm yếu kèm phân loại mức rủi ro. (Ngoài phạm vi gói Giám sát 24/7.)

| Subtask | Mode | Đầu vào | Phải nộp | Chấm |
|---|---|---|---|---|
| **T1341.001** | file | HV-16 bản xuất cấu hình K mục, M không an toàn | `insecure[]` | set_delta |
| **T1341.002** | file | HV-16, HV-39 | `insecure[]`, `risk{}` | 0.7 / 0.3 |
| **T1341.003** | vm | HV-12 16 18 26 28 35 37 38 39 | `observations{insecure, risk}`, `actions` chỉ `read` | (0.7 + 0.3) × **[máy không đổi]** — verifier so SHA-256 cây cấu hình trước/sau |

**Danh mục cấu hình không an toàn cần nhận ra**

| Điểm yếu | Cấu hình | Vì sao nguy hiểm |
|---|---|---|
| **WDigest** | `HKLM\SYSTEM\CurrentControlSet\Control\SecurityProviders\WDigest\UseLogonCredential = 1` | mật khẩu dạng rõ trong LSASS ⇒ dump credential |
| **Accessibility Features** | `Image File Execution Options\sethc.exe` (hoặc `utilman.exe`, `osk.exe`, `magnify.exe`, `narrator.exe`) có `Debugger`, hoặc binary bị thay | backdoor màn hình đăng nhập (sticky keys) |
| **IIS Machine Key bị lộ** | `<machineKey validationKey=… decryptionKey=…>` trong `web.config` trùng khoá đã công bố công khai | giả mạo ViewState ⇒ thực thi mã từ xa |
| Khác (khi bản xuất có) | SMBv1 bật · LLMNR/NBT-NS bật · RDP không NLA · LSA protection (`RunAsPPL`) tắt · `AlwaysInstallElevated = 1` · `AutoAdminLogon` kèm `DefaultPassword` · tài khoản Guest bật | mở đường xâm nhập/leo thang |

- Nộp tên mục **đúng như trong bản xuất** (key/ID mục cấu hình; so chữ thường). set_delta ⇒ chỉ liệt
  kê mục thực sự không an toàn — giá trị mặc định an toàn hoặc đã vá không đưa vào.
- **`risk{}` (.002/.003):** tra **ma trận HV-39** — xếp mức theo khả năng bị khai thác × tác động (vd
  machine key lộ trên máy chủ web phơi internet ⇒ cao nhất). Dùng đúng nhãn mức của ma trận.
- **.003:** chỉ đọc — không "sửa luôn cho an toàn". Sửa cấu hình là việc của IR theo kế hoạch khắc phục.

---

## T0292 — Khuyến nghị biện pháp khắc phục lỗ hổng

Chỉ ra cụ thể điểm yếu/lỗ hổng mà attacker **đã lợi dụng**, kèm hướng dẫn khắc phục từng điểm. Đầu ra:
danh mục điểm yếu kèm hướng dẫn khắc phục cụ thể.

| Subtask | Mode | Đầu vào | Phải nộp | Chấm |
|---|---|---|---|---|
| **T0292.001** | file | HV-12 ticket lỗ hổng | `priority` | enum 1.0 |
| **T0292.002** | file | HV-12, HV-37 | `priority`, `exposure_path` | 0.6 / 0.4 |
| **T0292.003** | soc (SIEM, Quản lý lỗ hổng) | HV-02 12 16 28 37 38 39 | `exploited`, `priority`, `mitigations[]`, `citations[]` | (0.4·exploited × **CITE** + 0.3 + 0.3) |

**Ưu tiên khắc phục theo rủi ro, không theo CVSS thuần**
1. Mức nghiêm trọng kỹ thuật (CVSS, có exploit công khai/đang bị khai thác ngoài thực tế).
2. **Phơi nhiễm** — có đường từ vùng không tin cậy tới dịch vụ không (HV-37: internet → DMZ → host;
   firewall, NAT, phân vùng)? **Bẫy .002: CVSS 9.8 nhưng không phơi ra ngoài ⇒ ưu tiên đúng là Thấp.**
3. **Giá trị tài sản** (HV-38: cấp độ hệ thống, core, VIP) và kiểm soát bù trừ.
4. `exposure_path` = đường tiếp cận đã xác định (hoặc nhãn "không phơi") — chọn trong `options`.

**.003 — đã bị khai thác trước khi vá chưa?**
- Tìm trong log lịch sử (HV-02, HV-28 web/WAF) **request khai thác đúng lỗ hổng** trước mốc vá, và
  **hậu quả** trên máy (HV-16: file/service/task mới). Có ⇒ `exploited` đúng; câu trả lời phải kèm
  **dẫn chứng grep được** — trường `exploited` nhân gate CITE.
- `mitigations[]` — tập hành động cụ thể (vá/nâng phiên bản, tắt tính năng, chặn tại WAF/firewall, đổi
  khoá/thông tin đăng nhập bị lộ, rà lại máy nếu đã bị khai thác). Viết dạng hành động ngắn, đúng tập
  nhãn của đề nếu có.

## Bẫy hay gặp

- Báo đầu gần (local address) thay vì đầu xa; báo cả kết nối nội bộ RFC1918.
- Ở bài vm: "tiện tay" kill tiến trình/sửa cấu hình ⇒ ×0.
- Liệt kê mọi mục cấu hình "nghe có vẻ yếu" thay vì mục thực sự sai trong bản xuất.
- Xếp ưu tiên theo CVSS mà bỏ qua phơi nhiễm và giá trị tài sản.
- Khẳng định "đã bị khai thác" không kèm trích dẫn.
