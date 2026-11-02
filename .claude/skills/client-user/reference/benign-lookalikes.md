# Client · Hoạt động hợp lệ dễ bị nhầm là tấn công

Đây là những việc **hoàn toàn hợp lệ** mà SOC thật vẫn thường báo nhầm. Bạn thực hiện chúng **đúng vai** và
**khớp với ngữ cảnh hợp lệ mà kịch bản đã cung cấp** — chính ngữ cảnh đó (change ticket, whitelist, lịch, hồ sơ
chiến dịch) là thứ blue phải tìm ra để kết luận FP. Không bao giờ tự tạo ngữ cảnh giả, không làm biến thể độc hại.

Cột "Blue sẽ kiểm" nêu ngữ cảnh tham khảo, không bảo đảm blue phải kết FP. Không tự chọn hoạt động gây nhiễu nếu
không phục vụ công việc được giao. Tên tool, chữ ký, whitelist, CDN hay port quen không tự chứng minh hợp lệ.

## Quản trị hệ thống

| Hoạt động | Ngữ cảnh hợp lệ đi kèm | Blue sẽ kiểm |
|---|---|---|
| Quản trị từ xa bằng PsExec / WMI / PowerShell remoting / RDP | đi từ **jump host/PAM**, tài khoản admin được phép, trong **change window** có ticket | máy nguồn có phải jump host, có ticket, đúng giờ |
| Triển khai hàng loạt bằng SCCM / Ansible | lịch triển khai, máy chủ quản trị chuẩn | nguồn là máy chủ triển khai, đúng lịch |
| Script quản trị chạy theo lịch | lịch trong hệ thống tác vụ | đúng giờ, đúng tài khoản |
| Dùng công cụ quản trị bị AV gắn PUA (PsExec, NirSoft) | công cụ có chữ ký, nằm trong whitelist, admin dùng | chữ ký, whitelist, người dùng |
| Tạo tài khoản dịch vụ mới | change ticket | ticket, người tạo |
| Triển khai script lên web (`health.php`, `status.aspx`, `api.jsp`, `login.php`) | yêu cầu triển khai | nội dung lành tính, người triển khai |
| Cài agent/phần mềm mới cho cả nhóm máy | change ticket — sẽ làm một số rule bắn nhiều hơn bình thường | thời điểm FP tăng trùng thời điểm triển khai |

## Đăng nhập và thông tin đăng nhập

| Hoạt động | Ngữ cảnh | Blue sẽ kiểm |
|---|---|---|
| Gõ sai mật khẩu 1–3 lần rồi đăng nhập đúng | người dùng thường, máy quen | ít lần, cùng máy, cùng giờ làm việc |
| Tài khoản dịch vụ dùng mật khẩu đã hết hạn, lỗi lặp lại đều đặn | service account đã biết | nhịp lặp máy móc, không có lần thành công lạ |
| Agent AV/backup đọc tiến trình lsass | agent có chữ ký, nằm trong whitelist | tiến trình đọc lsass là agent hợp lệ |
| Đăng nhập VPN từ IP nước ngoài | nhân viên có lịch công tác | lịch công tác, thiết bị quen |
| Lãnh đạo đăng nhập ngoài giờ | vai VIP, thiết bị quen | thiết bị, vị trí, hành vi sau đăng nhập |

## Dò quét và giám sát hợp lệ

| Hoạt động | Ngữ cảnh | Blue sẽ kiểm |
|---|---|---|
| Quét lỗ hổng bằng Nessus/Qualys | IP scanner trong danh mục, **đúng lịch quét** | nguồn và lịch |
| Health-check của Zabbix/load balancer | máy giám sát đã biết | nhịp đều, đích là dịch vụ được giám sát |

## Web và ứng dụng

| Hoạt động | Ngữ cảnh | Blue sẽ kiểm |
|---|---|---|
| Ô tìm kiếm chứa ký tự đặc biệt (`' " < >`) hoặc từ SQL (`select your plan`) | người dùng bình thường | không phải tổ hợp tấn công, không có thay đổi phía máy chủ |
| Dùng framework có tệp PHP chứa `eval` | tệp gốc của framework | hash khớp bản phát hành gốc |

## Email

| Hoạt động | Ngữ cảnh | Blue sẽ kiểm |
|---|---|---|
| Nhận và mở email marketing hợp lệ | nhà gửi đã biết | SPF/DKIM hợp lệ, không có đăng nhập lạ sau click |
| Đội nhận thức ATTT chạy chiến dịch phishing giả lập; nhân viên click | **hồ sơ chiến dịch** của khách hàng | email thuộc chiến dịch đã đăng ký |

## Mạng

| Hoạt động | Ngữ cảnh | Blue sẽ kiểm |
|---|---|---|
| Đồng bộ thời gian (NTP), gửi telemetry, health-check — lưu lượng **có chu kỳ đều** | máy chủ thời gian/telemetry đã biết | đích hợp lệ, tiến trình hợp lệ |
| AV tra cứu cloud bằng DNS dài | domain của hãng AV | domain thuộc hãng |
| Bản ghi TXT xác thực domain | quản trị DNS | đúng domain của tổ chức |
| SSH/VPN quản trị (kể cả port forward) | admin, jump host | người dùng, máy nguồn |
| Truy cập nội dung qua CDN dùng chung | duyệt web bình thường | hạ tầng dùng chung, không phải đích riêng |
| Backup/đồng bộ cloud dung lượng lớn ra ngoài | lịch backup | đích là kho backup đã biết, đúng lịch |

## Tệp, tiến trình, khởi động cùng hệ thống

| Hoạt động | Ngữ cảnh | Blue sẽ kiểm |
|---|---|---|
| Cài phần mềm đóng gói bằng packer thương mại | phần mềm có chữ ký | chữ ký, nguồn tải |
| Dùng bundle JS đã minify, template engine (Jinja) dùng `eval`/`base64` | ứng dụng nội bộ | nguồn gốc, luồng dữ liệu và mục đích thực tế; API nhạy cảm chưa đủ kết luận độc |
| Đợt kiểm thử AV dùng **tệp EICAR** | hồ sơ đợt kiểm thử | chuỗi EICAR chuẩn, đúng đợt |
| Tác vụ cập nhật (GoogleUpdate, OneDrive), cron `certbot`/`logrotate`/`backup-db`, service agent backup, `Teams.lnk` trong Startup | phần mềm đã cài hợp lệ | binary đích có chữ ký, tiến trình tạo mục là installer hợp lệ |
| Ứng dụng .NET/Java/trình duyệt chạy bình thường (có vùng nhớ RWX do JIT) | ứng dụng hợp lệ | runtime JIT đã nạp, không có PE header lạ trong vùng nhớ |

## Không phải việc của client

- **Pentest có phép** và payload bắn vào máy đã vá: đó là hoạt động tấn công (dù hợp lệ) — do red team thực hiện kèm
  giấy phép trong kịch bản.
- Domain đã sinkhole, IOC hết hạn, sandbox email tự mở URL: đó là hành vi của hạ tầng bảo mật/TI, do range cấu hình.
