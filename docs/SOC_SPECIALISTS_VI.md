# Bổ sung chuyên môn và quy trình SOC

Phạm vi: nâng continuous application lab từ các vai tổng quát thành đội có chuyên môn,
có công cụ lấy chứng cứ, nhiệm vụ/bàn giao và trạng thái làm việc thực sự. Giữ cấu hình
cũ, catalog 175 subtask và dữ liệu run hiện có. Không coi tên skill là tích hợp sản phẩm.

## Các checkpoint triển khai

| Bước | Nội dung | Trạng thái |
|---|---|---|
| 1 | Query phân trang, cutoff/world scope, lấy evidence và case cũ, finding, đóng FP/mở lại | Đã có code và test HTTP |
| 2 | 12 chuyên môn blue, cấu hình agent kiêm nhiệm, nạp skill theo nhiệm vụ | Đã có registry, skill, phân quyền và test |
| 3 | Nhiệm vụ có nhận việc/bàn giao/kết quả, memory, wait và hoàn tất có hiệu lực | Đã có state machine; đang kiểm hồi quy |
| 4 | Artifact, kiểm rule, sức khoẻ telemetry và xác nhận phục hồi trong lab | Đang triển khai |
| 5 | Agent-office, README, smoke đầu cuối và kiểm tra hồi quy | Tiếp theo |

## Chứng cứ và case

Blue dùng `query_events` với `world_id`, `as_of_tick`, bộ lọc và `after_id`; kết quả theo
thứ tự tăng dần, có cursor và cờ giới hạn retention. Không có SQL tùy ý hoặc quyền đọc
sealed archive. `get_evidence` lấy event còn giữ hoặc bản sao đã gắn vào case.

`get_case` lấy case ngoài cửa sổ observation. `append_evidence` giữ dữ liệu cũ và thêm
event có thật; `record_finding` ghi claim/citation/severity/việc tiếp theo. Các cập nhật
cần `expected_revision` để tránh ghi đè quyết định mới hơn. Finding là kết luận analyst,
không thay ground truth của evaluator. Lead có thể đóng FP có dẫn chứng và mở lại case;
case có tác động vẫn phải qua kiểm chứng phản ứng khi đóng theo trạng thái resolved.

Quyền giới hạn trong một world được xác thực bởi HTTP capability. Một world hiện là một
lab dùng chung; đây chưa phải giải pháp SOC nhiều khách hàng có phân quyền tenant riêng.

## Chuyên môn

Blue có 12 chuyên môn: `lead`, `monitor`, `hunter`, `dfir`, `ir`, `content`, `malware`,
`network`, `intel`, `platform`, `identity`, `recovery`. Sáu vai mặc định giữ nguyên;
DFIR dùng `soc-dfir` riêng. Bảy skill mới đưa tổng repo lên 18 skills (15 nghiệp vụ,
3 phát triển), vẫn dùng 25 reference có sẵn để không sao chép handbook.

Operator cấu hình kiêm nhiệm trong world config, ví dụ:

```json
{"id":"blue-analyst","team":"blue","role":"dfir","specialties":["network","malware"]}
```

Tool của actor là hợp quyền của các chuyên môn được cấu hình. Message/model không tự
thêm chuyên môn hay quyền. Skill đang dùng chuyển theo chuyên môn nhiệm vụ trong phạm
vi đó; toàn bộ skill đã cấu hình được preflight trước khi mở lab có model.

## Nhiệm vụ và vòng đời actor

Lead tạo task theo chuyên môn; bên nhận phải accept, chỉ có một task ACTIVE tại một
thời điểm. Kết quả cần dẫn chứng đã gắn vào case. Handoff đưa việc về OFFERED và bên
nhận phải chấp nhận; blocked có lý do, lead có thể cancel và giao việc thay thế. Deadline
là tick của lab, không được tự chuyển thành SLA phút của khách hàng.

Notebook riêng tồn tại qua restart, có 200 mục/actor, phân trang và báo đầy rõ ràng;
không bị ghi đè bởi note 1.000 ký tự của planner. Notebook không hiện trong office/team.

`wait` tạm ngừng actor theo tick; `finish` dừng tới khi resume. Plan rỗng hợp lệ được
chuyển thành wait một tick. Model lỗi hoặc plan sai vẫn có fallback. In-flight plan
mang generation của actor: đổi nhiệm vụ/trạng thái sẽ vô hiệu hóa quyết định cũ.

Lead được resume đồng đội blue. Operator có thể resume bất kỳ actor trong world đã dừng:

```powershell
uv run saber world actor-resume --out runs/world --actor red-impact
```
