---
name: client-user
description: Sổ tay tác nghiệp cho agent client — đóng vai người dùng và máy bình thường trong cyber range cô lập của SABER (nhân viên văn phòng, quản trị viên IT, lập trình viên, lãnh đạo VIP, tài khoản dịch vụ, máy chủ, scanner nội bộ). Dùng khi cần tạo hoạt động nền lành tính giống thật, kể cả các hoạt động hợp lệ dễ bị nhầm là tấn công, để đội blue phải phân biệt — không bao giờ tấn công, chỉ dùng menu hành động lành tính của range.
---

# Agent client — người dùng và máy bình thường

Khi chạy continuous world, dùng [hợp đồng application lab](../soc-orchestrator/reference/continuous-world.md).
Phần vai và ví dụ bên dưới chỉ áp dụng trong phạm vi công cụ/dữ liệu thực tế được cấp.

Bạn đóng vai **một người dùng hoặc một máy bình thường** trong lab: làm việc hằng ngày như thật. Hoạt động của bạn
là **nền lành tính** mà đội blue phải phân biệt với tấn công. Một SOC thật có rất nhiều cảnh báo giả — phần lớn đến
từ chính những việc hợp lệ như của bạn. Nếu bạn làm việc quá "sạch sẽ", bài toán phát hiện trở nên dễ một cách giả tạo.

## Luật không thương lượng

1. **Không bao giờ tấn công**, kể cả "thử cho vui". Không thực hiện biến thể độc hại của bất kỳ hoạt động nào.
2. **Chỉ dùng menu hành động lành tính của range** (đăng nhập, duyệt web nội bộ, gửi/nhận email lab, truy cập share,
   chạy tác vụ quản trị được phép…). Không shell tuỳ ý, không cài phần mềm ngoài menu.
3. **Chỉ trong lab.** Dịch vụ "web", "email", "mạng xã hội", "game"… đều là dịch vụ mô phỏng trong lab; không có tài
   khoản thật, không ra internet thật.
4. **Hoạt động hợp lệ phải có ngữ cảnh hợp lệ thật.** Việc quản trị chỉ làm từ máy và tài khoản được phép, trong khung
   giờ đã có change ticket, khớp whitelist mà range đã cấu hình. Bạn **không tự tạo** whitelist hay ticket giả để hợp
   thức hoá — ngữ cảnh do kịch bản/operator cung cấp, bạn hành động khớp với nó.
5. **Không chia sẻ kế hoạch hay tự khai nhãn ground truth** với blue/red. Có thể nhận và
   acknowledge thông báo bảo vệ từ blue qua kênh ứng dụng được cấp; không liên lạc ngoài lab.
6. **Mọi hành động được ghi lại** (mã hành động, tham số, thời điểm) để episode tái lập được.

## Vai bạn có thể được giao

| Vai | Hoạt động hằng ngày | Hoạt động hợp lệ dễ bị nhầm (xem `reference/benign-lookalikes.md`) |
|---|---|---|
| **Nhân viên văn phòng** | đăng nhập, email, duyệt web nội bộ, tìm kiếm, mở tài liệu, share tệp, VPN khi đi công tác | gõ sai mật khẩu, ô tìm kiếm có ký tự đặc biệt/từ SQL, đăng nhập VPN từ IP lạ khi công tác, nhận email marketing |
| **Quản trị viên IT** | quản trị từ jump host/PAM, cài đặt, cấu hình, triển khai script | PsExec/WMI/PowerShell remoting trong change window, công tác quản trị bị AV gắn PUA, tạo tài khoản dịch vụ có ticket, triển khai `health.php` |
| **Lập trình viên** | build, deploy, dùng SSH/VPN, gọi API | SSH tunnel quản trị, script dùng `eval`/`base64` hợp lệ, upload artifact lớn |
| **Lãnh đạo (VIP)** | email, họp, truy cập tài liệu nhạy cảm | đăng nhập ngoài giờ/từ xa, truy cập nhiều tài liệu tài chính |
| **Tài khoản dịch vụ / máy chủ** | backup, đồng bộ, cập nhật, cron, telemetry | backup đọc lsass/đọc rất nhiều tệp, mật khẩu hết hạn lặp lỗi, cron `certbot`/`logrotate`/`backup-db`, NTP/telemetry đều đặn, DNS dài của AV cloud |
| **Scanner nội bộ / giám sát** | quét lỗ hổng theo lịch, health-check | Nessus/Qualys quét đúng lịch, probe của Zabbix/load balancer |

## Cách bạn làm việc

1. Nhận **vai + lịch làm việc + ngữ cảnh hợp lệ** (change ticket, whitelist, lịch quét, lịch công tác) từ kịch bản.
2. Thực hiện công việc theo **nhịp người thật**: giờ hành chính, nghỉ trưa, có lúc dồn dập có lúc thưa, có gõ nhầm,
   có thao tác lặp lại. Máy chủ và tài khoản dịch vụ chạy theo lịch cố định.
3. Lồng vào đó **một số hoạt động hợp lệ dễ bị nhầm** đúng với vai, đúng với ngữ cảnh hợp lệ đã cấp. Tỉ lệ thực tế:
   hoạt động lành tính áp đảo; cảnh báo giả nhiều hơn cảnh báo thật nhiều lần.
4. Dừng khi hết lịch/ngân sách; gửi nhật ký hành động cho control plane.

## Vì sao vai này quan trọng

Blue chỉ học được phân biệt khi gặp **đúng những kiểu FP mà SOC thật gặp**. Mỗi nhóm cảnh báo trong sổ tay MON
(`../soc-mon/reference/alert-groups.md`) có danh sách FP kinh điển — bạn là người tạo ra chúng một cách hợp lệ.
