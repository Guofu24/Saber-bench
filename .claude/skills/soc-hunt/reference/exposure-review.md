# HUNT · Kết nối mạng, cấu hình không an toàn và lỗ hổng

## Kiểm tra kết nối mạng hiện hành

Kiểm kết nối mạng **đang mở** trên máy đích để phát hiện **kênh ra ngoài bất thường** và **kênh tunneling đang
được duy trì**. (Mảng việc này thuộc nhóm điều tra số; kết quả thường chuyển thẳng cho IR.)

1. Lấy bảng kết nối (`ss`, `netstat`, `lsof`) — **chỉ đọc**, không kill tiến trình, không đóng socket.
2. **Mỗi kết nối nhìn ở đầu xa**: IP đích + cổng đích, và **tiến trình** mở nó.
3. **Bất thường** khi: kết nối **ra địa chỉ ngoài** trên **cổng lạ** (4444, 1337, 6667, 9001, 8081, 53413…) từ
   **tiến trình không nên mở socket ra ngoài**. **Lành tính**: lưu lượng nội bộ RFC1918, endpoint SaaS/cập nhật đã
   biết trên 80/443, dịch vụ hạ tầng (53, 123, 389, 445).
4. **Gắn đúng tiến trình** — không biết tiến trình thì không chặn đúng chỗ. Loại kết nối khớp whitelist (đúng tiến
   trình **và** đúng đích).
5. **Kênh C2/tunnel trên máy đang chạy:**
   - **reverse shell** — `bash`/`sh`/`nc` có socket ra ngoài;
   - **`ssh -R`** — ssh có remote forward tới host ngoài;
   - **DNS tunnel** — tiến trình lạ gửi nhiều truy vấn DNS dài tới một domain (đối chiếu log DNS);
   - flow ra đều đặn tới một đích lạ.

```json
{"abnormal": [{"ip": "203.0.113.9", "port": 4444, "process": "bash"},
              {"ip": "198.51.100.7", "port": 22, "process": "ssh"}],
 "evidence": ["…"]}
```

## Rà soát cấu hình không an toàn (Compromise Assessment)

Rà các điểm yếu có thể bị lợi dụng để xâm nhập. Đầu ra: danh mục cấu hình sai/điểm yếu kèm mức rủi ro. (Việc
này nằm ngoài gói Giám sát 24/7 — thuộc CA.)

| Điểm yếu | Cấu hình cần nhận ra | Vì sao nguy hiểm |
|---|---|---|
| **WDigest** | `HKLM\SYSTEM\CurrentControlSet\Control\SecurityProviders\WDigest\UseLogonCredential = 1` | mật khẩu dạng rõ trong LSASS ⇒ dump credential |
| **Accessibility Features** | `Image File Execution Options\sethc.exe` (hoặc `utilman.exe`, `osk.exe`, `magnify.exe`, `narrator.exe`) có `Debugger`, hoặc binary bị thay | backdoor ở màn hình đăng nhập (sticky keys) |
| **IIS Machine Key đã lộ** | `<machineKey validationKey=… decryptionKey=…>` trong `web.config` trùng khoá đã bị công bố công khai | giả mạo ViewState ⇒ thực thi mã từ xa |
| Khác | SMBv1 bật · LLMNR/NBT-NS bật · RDP không NLA · LSA protection (`RunAsPPL`) tắt · `AlwaysInstallElevated = 1` · `AutoAdminLogon` kèm `DefaultPassword` · tài khoản Guest bật | mở đường xâm nhập/leo thang |

1. Ghi mục **đúng như tên trong bản xuất cấu hình**; chỉ ghi mục thực sự sai (giá trị mặc định an toàn hoặc đã vá
   thì không ghi).
2. **Xếp mức rủi ro** theo ma trận rủi ro của khách hàng: khả năng bị khai thác × tác động (vd machine key lộ trên
   máy chủ web phơi internet là cao nhất).
3. Trên máy thật: **chỉ đọc**, không "sửa luôn cho an toàn" — cấu hình cây trước và sau phải giống hệt. Sửa là việc
   của kế hoạch khắc phục (IR).

```json
{"insecure": ["WDigest\\UseLogonCredential", "IFEO\\sethc.exe\\Debugger"],
 "risk": {"WDigest\\UseLogonCredential": "Cao", "IFEO\\sethc.exe\\Debugger": "Nghiêm trọng"}}
```

## Khuyến nghị khắc phục lỗ hổng

Chỉ ra cụ thể điểm yếu/lỗ hổng mà attacker **đã lợi dụng**, kèm hướng dẫn khắc phục cho từng điểm.

**Ưu tiên theo rủi ro, không theo CVSS thuần**
1. Mức nghiêm trọng kỹ thuật: CVSS, có exploit công khai/đang bị khai thác ngoài thực tế.
2. **Phơi nhiễm:** có đường từ vùng không tin cậy tới dịch vụ không (sơ đồ mạng: internet → DMZ → host; firewall,
   NAT, phân vùng)? **CVSS 9.8 nhưng không phơi ra ngoài thì ưu tiên đúng có thể chỉ là Thấp.**
3. **Giá trị tài sản** (cấp độ hệ thống, core, VIP) và kiểm soát bù trừ đang có.
4. Ghi rõ **đường tiếp cận** đã xác định (`exposure_path`), hoặc "không phơi".

**Đã bị khai thác trước khi vá chưa?**
- Tìm trong log lịch sử (web/WAF, log thô) **request khai thác đúng lỗ hổng** trước mốc vá, và **hậu quả** trên máy
  (tệp/service/task mới). Có thì kết luận đã bị khai thác — **kèm dẫn chứng tìm lại được**; không có dẫn chứng thì
  không khẳng định.
- **Biện pháp** (`mitigations`): vá/nâng phiên bản · tắt tính năng · chặn tại WAF/firewall · đổi khoá/thông tin đăng
  nhập có thể đã lộ · rà lại máy nếu đã bị khai thác.

```json
{"priority": "Cao", "exposure_path": "internet → WAF → web-01",
 "exploited": "yes", "mitigations": ["vá lên bản 4.2.1", "đổi machineKey", "rà webshell trên web-01"],
 "evidence": ["…"]}
```

## Sai lầm thường gặp

- Báo đầu gần (địa chỉ local) thay vì đầu xa; báo cả kết nối nội bộ RFC1918.
- Kill tiến trình hay sửa cấu hình trong lúc rà.
- Liệt kê mọi cấu hình "nghe có vẻ yếu" thay vì mục thực sự sai trong bản xuất.
- Xếp ưu tiên theo CVSS mà bỏ qua phơi nhiễm và giá trị tài sản.
- Khẳng định "đã bị khai thác" không kèm dẫn chứng.

Nguồn nghiệp vụ: NICE T2012, T1341, T0292 (catalog SABER).
