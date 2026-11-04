# HUNT · Giả thuyết có thể bác bỏ và kết quả tái lập

Chọn khi có TI, finding, thay đổi môi trường hoặc khoảng trống detection. Hunt có thể bắt đầu không có alert;
“assume breach” là cách đặt câu hỏi, không phải kết luận hệ thống đã bị chiếm.
Input: hypothesis, scope/time, nguồn/retention, query engine, asset baseline và budget.

## Lập hunt card

`question / behavior hypothesis / benign alternative / expected observations / sources needed /
population+time window / query revision / disconfirming evidence / stop condition / owner`.
Ưu tiên hypothesis theo relevancy với môi trường và dữ liệu có thật; ATT&CK tag không thay executable query.
Nếu nguồn chưa có, đầu ra là collection/readiness request; không chạy query rỗng rồi báo sạch.

## Thực hiện

1. Xác minh tables/fields, clock, coverage, role permission và row caps. Chạy query hẹp trên một entity/window
   để kiểm logic; kiểm positive control khi có và benign near-match trước khi mở scope.
2. Pivot từ anchor sang session/process/resource với ID đúng namespace. Mở rộng theo evidence và budget,
   không quét mọi tenant hay mọi thời gian chỉ để tăng hits. Giữ query/cursor/revision/receipt.
3. So cùng nhóm chức năng/OS/ca làm việc khi có baseline. Rare/new không tự là malicious; so lịch deploy,
   service accounts, software distribution và sensor rollout trước khi gán hành vi cho adversary.
4. Kiểm giả thuyết đối lập và bằng chứng trái chiều. Query bị timeout/parser lỗi khác không có hits;
   sampling không chứng minh quần thể còn lại sạch. Raw event và alert phát sinh từ nó không độc lập.
5. Có ongoing harm thì bàn giao IR ngay, giữ hunt scope để rà các entity liên quan. Với finding chưa đủ,
   đề nghị phép kiểm phân biệt; không tự containment để “xác minh” giả thuyết chỉ đọc.

## Kết thúc và chuyển thành detection

Kết quả: supported trong phạm vi quan sát; contradicted trong phạm vi đủ quan sát; hoặc inconclusive.
Ghi population đã/ chưa rà, time range, gaps, findings/citations, exact query và chi phí/timeout.
Không viết “không bị xâm nhập” cho một hunt âm. Khi cần mở rộng, nêu dữ liệu nào có thể đổi kết luận.

Chuyển CNT một detection hypothesis có log dependency, positive/negative examples, grouping/window,
known benign pattern và giới hạn; không gửi nguyên IOC list thay cho use case. MON nhận dấu hiệu cần canh,
lead nhận risk/coverage. Đo useful findings, queries tái lập được, gaps đã xử lý và kết quả retest,
không đo thành công bằng số technique được tô màu.

Live read/collection có thể sinh access log, CPU/IO hoặc cache; ghi dấu chân công cụ. Chỉ đọc không đồng nghĩa
máy giữ nguyên mọi bit. Không sửa target ngoài quyền hoặc chạy collector mới vì tài liệu nhắc tên nó.

Ví dụ: nhiều PowerShell ngoài giờ → kiểm session/change window và behavior; automation hợp lệ có thể bác bỏ
claim hẹp, còn vùng thiếu script logs vẫn unknown. Không lọc hết PowerShell để làm số hits về 0.

Nguồn: [Microsoft Sentinel hunts](https://learn.microsoft.com/en-us/azure/sentinel/hunts),
[MITRE getting started](https://www.mitre.org/news-insights/publication/getting-started-attck).
