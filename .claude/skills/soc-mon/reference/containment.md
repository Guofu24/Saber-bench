# MON · Phản ứng nhanh: cô lập và gỡ mã độc

**Chỉ khi được cấp quyền trước.** Phản ứng nhanh của MON: cô lập toàn bộ kết nối mạng trên máy trạm người
dùng (**trừ máy người dùng VIP**), dừng hoặc tạm dừng tiến trình độc hại. IR cô lập máy chủ và ứng dụng bị
compromise. Không có quyền trước ⇒ **mỗi hành động phải xin phê duyệt từng lần** (chậm hơn, nhưng bắt buộc).
Mục tiêu: attacker mất khả năng điều khiển máy nhiễm, và không quay lại được bằng cách cũ.

## Cô lập máy nhiễm

**Chọn lớp cô lập**

| Lớp | Hành động | Dùng khi |
|---|---|---|
| endpoint / host | cô lập mạng bằng EDR (máy chỉ còn nói chuyện với console EDR) | mặc định cho máy trạm thường bị nhiễm |
| tiến trình | kill/suspend tiến trình độc, giữ máy chạy | máy **không được cô lập** (VIP) hoặc dịch vụ không được ngừng |
| mạng | chặn IOC/cổng tại firewall/proxy, cách ly VLAN | C2 dùng chung cho nhiều máy, hoặc không có EDR |
| tài khoản | vô hiệu hoá tài khoản bị chiếm | tài khoản đang bị dùng để di chuyển |

**Ba ràng buộc cứng — vi phạm một cái là hỏng cả phản ứng**
1. **Không cô lập máy VIP.** Tra danh mục tài sản; với máy VIP dùng lớp tiến trình/mạng thay cho cô lập host và
   ghi rõ lý do.
2. **Thu ảnh bộ nhớ trước khi cô lập.** Cô lập hay kill trước sẽ mất bằng chứng trong RAM (kết nối, tiến trình
   bị inject). Thứ tự luôn là `memory_dump` → `isolate`.
3. **Không chặn dải mạng chứa hệ thống cấp độ 3.** Chặn đúng IP/host cụ thể, không chặn cả CIDR rộng.

**Kế hoạch hành động** — danh sách `{action, object, layer}`, không thêm hành động thừa:

```json
{"isolation_layer": "endpoint",
 "actions": [
  {"action": "memory_dump", "object": "ws-acc-07", "layer": "endpoint"},
  {"action": "isolate", "object": "ws-acc-07", "layer": "endpoint"},
  {"action": "block", "object": "203.0.113.9", "layer": "firewall"}
 ],
 "vip_rule": "ws-ceo-01 là VIP — chỉ kill tiến trình, không cô lập host",
 "memdump_first": "yes", "tier3_range": "không chặn 10.10.0.0/16 (chứa hệ thống cấp 3)"}
```

## Gỡ mã độc (eradication trên máy)

Xoá mã độc trên máy chủ/máy trạm và webshell trên máy chủ; trong IR đây là bước Eradication, đi kèm vá lỗ hổng
và cấu hình lại điểm yếu (phần đó xem `soc-ir`).

**Quy trình gỡ sạch**
1. **Xác định tập tệp độc** bằng hash + metadata, không bằng tên: thư mục nguy cơ (`/tmp`, `/var/tmp`,
   `/dev/shm`, AppData, Temp), không chữ ký, hash khớp IOC/báo cáo phân tích mã độc.
2. **Xác định kênh tự phục hồi**: `/etc/cron.d/*`, crontab người dùng, unit `systemd` (service, timer),
   `/etc/profile.d/*.sh`, `.bashrc`, Run key, service, scheduled task — mục nào trỏ tới hoặc tải lại binary độc.
   **Gỡ cả mục persistence lẫn binary**; chỉ xoá binary thì mã độc quay lại.
3. **Giữ nguyên mục hợp lệ**: cron `certbot`, `logrotate`, `backup-db`, unit của agent backup. Xoá nhầm tệp sạch
   hay tệp cấu hình là gây sự cố mới.
4. **Xoá hẳn, không di chuyển.** Chuyển tệp độc sang thư mục khác không phải là gỡ — quét toàn máy theo nội dung
   vẫn thấy nó.
5. Không sửa tệp cấu hình hợp lệ, trừ khi kế hoạch yêu cầu khôi phục cấu hình bị attacker sửa.
6. **Xác minh sau khi gỡ**: hash của tệp độc không còn ở bất kỳ đâu trên máy; mọi tệp sạch còn nguyên byte; kênh
   tự phục hồi đã hết.

```json
{"actions": [
  {"op": "remove", "path": "/tmp/.x/agentd"},
  {"op": "remove", "path": "/etc/cron.d/agentd-refresh"},
  {"op": "remove", "path": "/etc/systemd/system/agentd.service"}
 ],
 "kept": ["/etc/cron.d/certbot", "/etc/cron.d/logrotate"],
 "verified": "không còn hash độc trên toàn máy; tệp sạch nguyên vẹn"}
```

## Sai lầm thường gặp

- Cô lập host máy VIP; cô lập trước khi thu RAM; chặn cả /16 chứa hệ thống cấp 3.
- Xoá binary mà để lại cron/systemd/profile.d.
- Xoá nhầm `logrotate`/`certbot`/`backup-db` vì "trông giống cron lạ".
- "Dọn" bằng cách chuyển tệp sang thư mục khác.

Nguồn nghiệp vụ: NICE T1388, T1389 (catalog SABER).
