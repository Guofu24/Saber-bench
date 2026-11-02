# HUNT · Kết nối mạng, cấu hình không an toàn và lỗ hổng

## Kiểm tra kết nối mạng hiện hành

Kiểm kết nối mạng **đang mở** trên máy đích để phát hiện **kênh ra ngoài bất thường** và **kênh tunneling đang
được duy trì**. (Mảng việc này thuộc nhóm điều tra số; kết quả thường chuyển thẳng cho IR.)

1. Lấy bảng kết nối (`ss`, `netstat`, `lsof`) — **chỉ đọc**, không kill tiến trình, không đóng socket.
2. **Mỗi kết nối nhìn ở đầu xa**: IP đích + cổng đích, và **tiến trình** mở nó.
3. Đối chiếu đích, chiều, cổng, giao thức, tiến trình/chủ sở hữu và baseline. Địa chỉ RFC1918 hay cổng 80/443/53/445
   không bảo đảm lành tính: vẫn có thể là C2 hoặc di chuyển ngang. Cổng lạ cũng không tự chứng minh độc hại.
4. **Gắn đúng tiến trình và thời điểm**; PID có thể được tái sử dụng. Kiểm whitelist đúng tiến trình, đích, vai và
   lịch, đồng thời xem hành vi thực tế. Thiếu process mapping thì ghi hạn chế, không tự đoán để chặn.
5. **Kênh C2/tunnel trên máy đang chạy:**
   - **reverse shell** — `bash`/`sh`/`nc` có socket ra ngoài;
   - **`ssh -R`** — ssh có remote forward tới host ngoài;
   - **DNS tunnel** — tiến trình lạ gửi nhiều truy vấn DNS dài tới một domain (đối chiếu log DNS);
   - flow ra đều đặn tới một đích lạ.
   Đây là đầu mối cần xác minh mục đích/quyền và dữ liệu liên quan; C2 không bắt buộc dùng cổng lạ hay nhịp đều.

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
   NAT, phân vùng)? Xét cả đường từ máy nội bộ đã bị chiếm. CVSS 9.8 có thể được hạ ưu tiên theo ma trận và
   kiểm soát bù trừ đã kiểm chứng; không tự xếp Thấp chỉ vì không phơi internet.
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

- Nhầm đầu gần với đầu xa; bỏ qua kết nối nội bộ chỉ vì là RFC1918.
- Kill tiến trình hay sửa cấu hình trong lúc rà.
- Liệt kê mọi cấu hình "nghe có vẻ yếu" thay vì mục thực sự sai trong bản xuất.
- Xếp ưu tiên theo CVSS mà bỏ qua phơi nhiễm và giá trị tài sản.
- Khẳng định "đã bị khai thác" không kèm dẫn chứng.

Nguồn nghiệp vụ: NICE T2012, T1341, T0292 (catalog SABER).
