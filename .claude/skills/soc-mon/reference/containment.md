# MON · Phản ứng nhanh: cô lập và gỡ mã độc

**Chỉ trong quyền đã cấp.** MON world không có tool containment, phải bàn giao IR. Môi trường khác chỉ
thực thi khi capability/SOP cho phép; thiếu quyền thì chuyển người có quyền theo cơ chế hiện có.
Không xin lại authorization còn hiệu lực. Bảng và JSON dưới minh họa case có SOP tương ứng.
Mục tiêu: attacker mất khả năng điều khiển máy nhiễm, và không quay lại được bằng cách cũ.

## Cô lập máy nhiễm

**Chọn lớp cô lập**

| Lớp | Hành động | Dùng khi |
|---|---|---|
| endpoint / host | cô lập mạng bằng EDR (máy chỉ còn nói chuyện với console EDR) | mặc định cho máy trạm thường bị nhiễm |
| tiến trình | kill/suspend tiến trình đã xác minh, xét dependency | khi SOP hạn chế cô lập host hoặc service impact cần phương án khác |
| mạng | chặn IOC/cổng tại firewall/proxy, cách ly VLAN | C2 dùng chung cho nhiều máy, hoặc không có EDR |
| tài khoản | vô hiệu hoá tài khoản bị chiếm | tài khoản đang bị dùng để di chuyển |

**Kiểm ràng buộc của case/SOP trước hành động**
1. Case cấm cô lập VIP thì giữ nguyên, chọn lớp được phép và ghi lý do. Không mặc định kill process là an toàn
   cho dịch vụ. Ngoài SOP đó, VIP là yếu tố business impact, không tự thành cấm containment.
2. Case yêu cầu `memory_dump` → `isolate` thì tuân thủ. Trong sự cố khác, cân volatility, tác động collection
   và ongoing harm; isolation không đồng nghĩa luôn xóa RAM, kill có thể làm mất evidence. Escalate quyết định khẩn.
3. Giữ exclusions/dải mạng theo case. Ưu tiên đích hẹp và kiểm shared infrastructure; không block rộng theo IOC đơn lẻ.

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
1. **Xác định tập tệp cần xử lý** bằng behavior/context và evidence có hash/path/identity. Tên, thư mục,
   chữ ký hoặc AV label riêng lẻ chưa đủ; kiểm false positives và quyền trước khi xóa/quarantine.
2. **Xác định kênh tự phục hồi**: `/etc/cron.d/*`, crontab người dùng, unit `systemd` (service, timer),
   `/etc/profile.d/*.sh`, `.bashrc`, Run key, service, scheduled task — mục nào trỏ tới hoặc tải lại binary độc.
   **Gỡ cả mục persistence lẫn binary**; chỉ xoá binary thì mã độc quay lại.
3. **Giữ nguyên mục hợp lệ**: cron `certbot`, `logrotate`, `backup-db`, unit của agent backup. Xoá nhầm tệp sạch
   hay tệp cấu hình là gây sự cố mới.
4. Case yêu cầu remove thì thực hiện đúng trên bản lab được chỉ định. Ngoài ra chọn quarantine/removal/rebuild
   theo SOP và bảo toàn chứng cứ; đổi thư mục mà vẫn thực thi được chưa là containment. Quarantine không thể
   thực thi và kho evidence được kiểm soát có thể còn hash độc hợp lệ.
5. Không sửa tệp cấu hình hợp lệ, trừ khi kế hoạch yêu cầu khôi phục cấu hình bị attacker sửa.
6. **Xác minh trong phạm vi đã kiểm**: đường thực thi/tái tạo bị ngăn, cấu hình và tệp hợp lệ theo baseline;
   ghi evidence/quarantine và vùng chưa scan riêng. Không hứa đã tìm mọi bản sao hoặc máy hoàn toàn sạch.

```json
{"actions": [
  {"op": "remove", "path": "/tmp/.x/agentd"},
  {"op": "remove", "path": "/etc/cron.d/agentd-refresh"},
  {"op": "remove", "path": "/etc/systemd/system/agentd.service"}
 ],
 "kept": ["/etc/cron.d/certbot", "/etc/cron.d/logrotate"],
 "verified": "điền evidence kiểm sau thao tác; chưa verify thì ghi pending"}
```

## Sai lầm thường gặp

- Vi phạm exclusions/order của case; chặn rộng khi chưa xét service impact.
- Xoá binary mà để lại cron/systemd/profile.d.
- Xoá nhầm `logrotate`/`certbot`/`backup-db` vì "trông giống cron lạ".
- "Dọn" bằng cách chuyển tệp sang thư mục khác.

Nguồn nghiệp vụ: NICE T1388, T1389 (catalog SABER).
Khung quyết định thực tế: [NIST SP 800-61r3](https://csrc.nist.gov/pubs/sp/800/61/r3/final).
