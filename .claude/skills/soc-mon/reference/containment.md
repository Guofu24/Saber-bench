# MON · Phản ứng nhanh — T1388 (cô lập malware) · T1389 (loại bỏ malware)

**Chỉ khi được cấp quyền trước.** Quick response của MON: cô lập toàn bộ kết nối mạng trên máy trạm
người dùng (**trừ máy người dùng VIP**), dừng hoặc tạm dừng tiến trình độc hại; IR cô lập máy chủ và
ứng dụng bị compromise. Không có quyền trước thì **mỗi hành động phải xin phê duyệt từng lần**. Mục tiêu:
attacker mất khả năng điều khiển máy nhiễm, và (T1389) không xâm nhập lại được bằng cách cũ.

Trong benchmark mọi hành động là **khai báo**, áp lên snapshot/lab niêm phong — không bao giờ chạm máy
thật. Hành động trên hệ thống thật cần lab cô lập + phê duyệt (xem `docs/SECURITY.md`).

---

## T1388 — Cô lập malware

| Subtask | Mode | Đầu vào | Phải nộp | Chấm |
|---|---|---|---|---|
| **T1388.001** | file | HV-14, HV-38 | `isolation_layer`, `vip_rule` | [lớp đúng] × **[không cô lập máy VIP]** |
| **T1388.002** | file | HV-14, HV-37, HV-38 | `actions[]` `{action, object, layer}`, `vip_rule` | F1 × [VIP] |
| **T1388.003** | soc (EDR, Firewall) | HV-07 14 15 16 17 18 20 34 37 38 39 | `actions[]`, `vip_rule`, `memdump_first`, `tier3_range` | F1 × **Π[3 ràng buộc cứng]** |

**Chọn lớp cô lập** (dùng nhãn lớp đúng như `options`/đề):
- *Endpoint/host* — cô lập mạng bằng EDR (máy chỉ còn nói chuyện với console EDR). Mặc định cho máy
  trạm thường bị nhiễm.
- *Tiến trình* — kill/suspend tiến trình độc hại, giữ máy hoạt động. Dùng khi **không được cô lập máy**
  (VIP) hoặc dịch vụ không được ngừng.
- *Mạng* — chặn IOC/cổng tại firewall/proxy, cách ly VLAN. Dùng cho C2 dùng chung nhiều máy hoặc khi
  không có EDR.
- *Tài khoản* — vô hiệu hoá tài khoản bị chiếm.

**Ba ràng buộc cứng (.003 — vi phạm bất kỳ cái nào ⇒ 0 toàn bài)**
1. **Không cô lập máy VIP** (`vip_rule`): tra HV-38; với máy VIP dùng lớp tiến trình/mạng thay cho cô
   lập host, và ghi rõ trong hành động.
2. **Thu ảnh bộ nhớ trước khi cô lập** (`memdump_first`): cô lập/kill trước sẽ mất bằng chứng trong
   RAM (kết nối, tiến trình inject). Thứ tự hành động phải có `memory dump` **trước** `isolate`.
3. **Không chặn dải chứa hệ thống cấp 3** (`tier3_range`): một CIDR rộng có thể nuốt hệ thống cấp độ 3
   (HV-38/HV-37) ⇒ chặn đúng IP/host cụ thể, không chặn cả dải.

`actions[]` là tập `{action, object, layer}` (chuẩn hoá chữ thường) — ví dụ
`{"action": "memory_dump", "object": "ws-acc-07", "layer": "endpoint"}`,
`{"action": "isolate", "object": "ws-acc-07", "layer": "endpoint"}`,
`{"action": "block", "object": "203.0.113.9", "layer": "firewall"}`. F1 ⇒ không thêm hành động thừa.

---

## T1389 — Loại bỏ malware (mode vm)

Xoá mã độc trên máy chủ/máy trạm, xoá webshell. Trong IR đây là **Eradication**, kèm vá lỗ hổng và cấu
hình lại điểm yếu (phần đó ở `soc-ir`).

| Subtask | Mode | Đầu vào | Chấm (đều là trạng thái sau hành động) |
|---|---|---|---|
| **T1389.001** | vm | HV-18 | [M file độc biến mất] × **[N file sạch nguyên byte]** |
| **T1389.002** | vm | HV-16, HV-18 | Π[malware_gone, clean_intact, **persistence_gone**] — mã độc tự phục hồi qua cron + systemd + profile.d |
| **T1389.003** | vm | HV-02 14 15 16 18 28 33 34 | Π[malware_gone, clean_intact, persistence_gone, **no_relocate**] — verifier quét **toàn máy** theo content hash |

**Nộp:** `{"actions": [{"op": "remove", "path": "..."}], "observations": {...}}` (xem hợp đồng §9).

**Quy trình gỡ sạch**
1. **Xác định tập độc** bằng hash + metadata (HV-18), không bằng tên/đường dẫn: thư mục nghi (`/tmp`,
   `/var/tmp`, `/dev/shm`, AppData, Temp), không chữ ký, hash khớp IOC/HV-34.
2. **Xác định kênh tự phục hồi** (HV-16): `/etc/cron.d/*`, crontab người dùng, unit `systemd`
   (`/etc/systemd/system/*.service`, timer), `/etc/profile.d/*.sh`, `.bashrc`, Run key… — phần nào trỏ
   tới hoặc tải lại binary độc. Gỡ **cả mục persistence lẫn binary** — chỉ xoá binary thì nó quay lại.
3. **Phân biệt mục hợp lệ:** cron `certbot`, `logrotate`, `backup-db`, unit của agent backup — **không
   đụng**. Xoá một file sạch hoặc file cấu hình ⇒ `clean_intact` = 0 ⇒ toàn bài 0.
4. **Dùng `remove`, không dùng `move`.** Di chuyển file độc sang thư mục khác vẫn bị quét toàn máy theo
   content hash bắt được (`no_relocate`).
5. Không `modify` file cấu hình hợp lệ trừ khi đề yêu cầu khôi phục cấu hình.

## Bẫy hay gặp

- Cô lập host máy VIP; cô lập trước khi thu RAM; chặn cả /16 chứa hệ thống cấp 3.
- Xoá binary mà để lại cron/systemd/profile.d ⇒ mã độc tự phục hồi.
- Xoá nhầm `logrotate`/`certbot`/`backup-db` vì "trông giống cron lạ".
- "Dọn" bằng cách chuyển file vào thư mục khác.
