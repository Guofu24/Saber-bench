# Agent rút kinh nghiệm và phát hành skill trong world

Triển khai 2026-11-02. Mỗi actor có nhật ký trải nghiệm riêng. Khi đủ một đợt công việc,
worker có thể phân tích kết quả và đề xuất bài học. Bài học chỉ được phát hành sau bộ
kiểm thử quyết định do operator cấp. Đây là cập nhật hướng dẫn/bộ nhớ dùng model;
trọng số Gemini không thay đổi.

## Điều gì thực sự chạy

1. HTTP server ghi tool, status, event ID, target và phiên bản skill cho **chính actor
   đã thực thi**. Số lỗi HTTP là quan sát; không tự gán lỗi suy luận hay ground truth.
2. Đóng đợt khi complete/block task, finish, close case, đổi chuyên môn, đủ 50 thao tác,
   hết khoảng tick cấu hình hoặc kết thúc run. Snapshot gồm tối đa 50 thao tác và 5
   note riêng gần nhất tại thời điểm đóng. Note viết sau đó, kể cả cùng tick, không
   được đưa ngược vào đợt cũ.
3. Đợt có lỗi HTTP hoặc kết thúc task/case/mission được xếp chờ phân tích. Đợt thông
   thường vẫn được ghi nhận nhưng không mặc định tốn lượt gọi để tạo bài học.
4. Khi có `--llm`, một worker nền dùng provider/pool **của đúng đội**, chung ledger
   và `--call-budget` với planner. Client vẫn tiếp tục trong lúc worker chờ API.
   Model có thể trả `lesson: null`; hệ thống không ép tạo bài học từ mọi lỗi.
5. Đề xuất chứa phạm vi áp dụng, hướng dẫn ngắn, citations và giới hạn. ID dẫn chứng
   phải có trong snapshot của actor. Sai schema/citation, quota hoặc lỗi provider
   đưa việc về `DEFERRED`; không tự retry vô hạn và không ghi raw lỗi API.
6. Có replay suite phù hợp thì evaluator so skill hiện tại với skill thêm bài học.
   Bản đề xuất phải qua toàn bộ checks và cải thiện ít nhất một check thuộc nhóm
   repair. Qua gate mới có release; thiếu suite giữ `AWAITING_SUITE`.

Chế độ scripted ghi nhận/tổng hợp số liệu, không tự suy luận ra bài học và không đổi
policy Python theo lesson. Phần rút kinh nghiệm bằng ngôn ngữ cần model. Các test ở
repo dùng provider giả để kiểm cơ chế, không phải bằng chứng Gemini đã cải thiện.

## Skill mới được lưu và áp dụng thế nào

World lưu bản gốc bất biến và phần bài học đã phát hành trong `world.sqlite3`.
Một version có hash của nội dung, parent và receipt kiểm thử. Prompt gồm bản gốc cùng
lesson áp dụng có điều kiện; quyền tool vẫn do server quyết định. Lesson nằm trong
dữ liệu tư vấn của observation, không được nâng thành quyền hoặc thay system contract.

File `.claude/skills/.../SKILL.md` của repo không bị nhiều actor cùng sửa. Runtime
dùng **phiên bản skill cục bộ của world**; `learning export` xuất phần đề xuất thành
Markdown để review/commit vào source nếu cần. Release cục bộ không tự commit/push dữ
liệu học lên Git. Cơ chế hiện tại chưa tự chuyển release sang một world khác.

Epoch là tập phiên bản được chốt cho cả world. Sau khoảng tick cấu hình, chỉ chuyển
sang release mới khi **không còn case mở hoặc task OFFERED/ACTIVE/BLOCKED**. Vì các
actor dùng chung case, đây là điểm chuyển đồng bộ để giữ phép so sánh nhất quán.
Nếu luôn có case đang mở, release sẽ tiếp tục chờ; không ép đổi giữa cuộc điều tra.
Plan đang chờ được xóa và generation tăng khi đổi epoch; kết quả LLM cũ trả về muộn
bị loại. WAITING/DONE không tự chuyển thành ACTIVE. Epoch tồn tại qua restart.

Sửa file skill trong checkout không tự thay bản gốc của world cũ. World mới chụp bản
source mới. Rollback chọn release cũ cho epoch tiếp theo, giữ history và pin của case
đang mở; rollback không khôi phục tác động đã xảy ra trong môi trường.

## Dùng với world hiện có

Code mới bổ sung các trường mặc định tương thích cấu hình cũ:

```json
{"learning_enabled": true, "learning_interval_ticks": 30}
```

Muốn đổi hai trường này, cấu hình trước lần chạy đầu như các trường world khác.
Default bật ghi nhận; không có `--llm` thì không gọi API để học. Với world Gemini đã
được cấu hình, chạy lệnh `world run`/`env run` như trước: worker học dùng chung budget,
không tạo pool hoặc ngân sách mới. Counters LLM gồm cả planning, reflection và replay;
số action LLM không đồng nghĩa số lượt gọi.

Chạy mẫu offline trong thư mục mới:

```powershell
uv run saber world init --out runs/learning-demo --clients 2 --blue-specialists
uv run saber world run --out runs/learning-demo --ticks 30
uv run saber world learning status --out runs/learning-demo
```

`status` đọc snapshot và dùng được khi world đang chạy. Các lệnh còn lại dùng khóa
writer và cần world đã dừng. Không có bước tự xin phê duyệt từng bài học: khi operator
đã cấp suite, code tự đánh giá/phát hành theo gate.

## Cấp bộ kiểm thử

```powershell
uv run saber world learning install-suite --out runs/learning-demo --file config/learning/client-session.json
```

Mẫu `client-session.json` kiểm đăng nhập trước tác vụ cần phiên, tiếp tục công việc
khi đã đăng nhập và xử lý chỉ dẫn giả trong tài liệu. Mẫu có 3 tình huống, lặp 2 lần:
**12 lượt gọi tối đa cho một evaluation**, cộng 1 lượt reflection nếu cần tạo đề xuất.
Provider có retry thì tổng HTTP attempts có thể cao hơn và vẫn bị chặn bởi budget.

Mỗi suite khai báo skill, mô tả, repetitions (2–3) và 3–12 case. Cần ít nhất một
`repair` và hai `regression` với observation khác nhau. Case gồm observation và các
next action chấp nhận được trong `expected`. Evaluator chỉ gửi observation, tool menu
thực của actor và phiên bản skill cho model; không gửi `expected`, tên split hay
kết quả chấm. Không cho agent tự sửa/install suite.

Gate yêu cầu đúng **một** next action hợp lệ, tool/args khớp một đáp án trong suite;
plan kèm hành động trái quyền không được lọc rồi coi là pass. Tất cả check của candidate
phải qua trên mọi lượt lặp, baseline phải trượt ít nhất một repair check. Hai bên dùng
cùng model ID; thứ tự gọi luân phiên. Không có cải thiện thì `REJECTED`, kể cả cả hai
bản đều đúng. Nếu head đã đổi thì proposal `STALE`, không tự chồng lên bản khác.

**Giới hạn:** đây là replay quyết định kế tiếp trên snapshot đã cấp, không thực thi
chuỗi tool và không chứng nhận xử lý SOC đầu cuối. Mẫu phát triển công khai không phải
holdout bí mật hay gold của 175 subtask. Operator cần xây suite có phản chứng và độ phủ
phù hợp; một bài học qua suite nhỏ vẫn có thể sai ở tình huống khác. Không dùng đáp án
benchmark kín để tạo guidance, không ghi đáp án kiểm thử vào notebook của actor.

## Xử lý hàng đợi sau lượt chạy

Run hữu hạn bình thường đóng journal và chờ một batch học nhỏ (tối đa 4 job, cửa sổ
chờ 30 giây). Công việc còn lại giữ trong DB. Một job là reflection hoặc evaluation,
không phải một HTTP call. STOP/Ctrl+C không khởi động batch hậu xử lý; request đang
bay dừng theo timeout transport. Lượt tiếp theo tiếp tục việc còn chờ.

Nếu chỉ muốn xử lý hàng đợi mà không cho actor hoạt động, dùng chế độ sau khi đã chọn
budget/model. Đây là lệnh **gọi API thật**, không cần chạy để kiểm thử offline:

```powershell
uv run saber world run --out runs/learning-demo --learning-only --learning-jobs 4 --llm --key-pool keys_pool.txt --call-budget 200
```

`--learning-only` giữ nguyên tick và file STOP. Budget `200` vẫn là trần tích lũy của
world, gồm các lượt trước; `report.json` cập nhật usage sau batch. Một batch có thể dừng
sớm hoặc để việc deferred; đọc status
để phân biệt. Không hứa xử lý toàn bộ queue chỉ bằng một lần gọi lệnh.

## Xem đề xuất, export, retry và rollback

```powershell
uv run saber world learning list --out runs/learning-demo
uv run saber world learning inspect --out runs/learning-demo --proposal PROPOSAL_ID
uv run saber world learning versions --out runs/learning-demo --skill client-user
uv run saber world learning export --out runs/learning-demo --proposal PROPOSAL_ID --file runs/review/lesson.md
uv run saber world learning retry --out runs/learning-demo --kind episode --id EPISODE_ID
uv run saber world learning rollback --out runs/learning-demo --skill client-user --version VERSION_ID
```

Thay các ID bằng giá trị thật từ kết quả. `list` có cả episode IDs; `inspect` trả nội
dung đề xuất và kết quả kiểm thử cho operator, không đưa vào observation của agent.
`retry --kind proposal` dùng cho evaluation
DEFERRED; retry có lịch sử và không reset provider usage. Export từ chối ghi đè file.
Database giữ trạng thái:

| Đối tượng | Trạng thái |
|---|---|
| Episode | RECORDED, PENDING, REFLECTED, NO_LESSON, DEFERRED |
| Proposal | AWAITING_SUITE, PUBLISHED, REJECTED, STALE, DEFERRED |

`learning.json` chứa số lượng/trạng thái, version IDs và epoch, không có nội dung
notebook/lesson. Agent-office hiển thị số lượt tổng kết, đề xuất và bản phát hành theo
actor. Bản phát hành có thể vẫn chờ được áp dụng ở epoch tiếp theo.

Giới hạn: 200 episode đang chờ; journal 50 thao tác/actor; lesson tối đa 8/version và
tổng context trong trần world. Khi đầy, báo backpressure/không thêm, không tự xóa
bằng chứng cũ. Disk budget chung vẫn dừng world khi đạt trần. Đây chưa phải kho kinh
nghiệm vô hạn hay hệ thống tự nén mọi bài học.

## Kiểm chứng và checkpoint

Test HTTP/fake provider bao phủ citation giả, riêng tư giữa đội, note tương lai cùng
tick, thiếu suite, hồi quy, phát hành, đổi epoch, plan cũ, rollback, CLI và worker chậm.
Không đọc key pool hay gọi Gemini thật trong lượt triển khai này.

Kết quả: **174 test Python + 9 test JavaScript qua**; các kiểm tra CLI bổ sung sau bộ
hồi quy cũng qua. Viewer build thành công; Ruff lint/format, mypy (162 source files),
audit 18 skills / 15 nghiệp vụ / 25 reference và frozen catalog 175 subtask đều PASS.
Artifact cục bộ: `runs/agent-learning/audit.json`, `runs/agent-learning/regression.xml`.
Các artifact run không commit. Test pipeline dùng provider giả có đáp án kiểm soát;
chưa đo chất lượng reflection, replay hay mức cải thiện SOC của Gemini thật.

```powershell
uv run pytest -o addopts= tests/world/test_learning.py tests/world/test_learning_pipeline.py tests/world/test_learning_cli.py -q
uv run python scripts/check_skills.py --out runs/agent-learning/audit.json
```

- `38384cb`: journal riêng và phiên bản skill bất biến.
- `7c67814`: worker reflection, replay gate và phát hành.
- `4cc90a1`: loại bỏ kế hoạch cũ khi đổi epoch.
- `729546f`: chốt notebook đúng thời điểm đóng đợt.
- `cb1db65`: CLI quản lý, suite mẫu, learning-only và counters office.
- `5ef203d`: báo cáo usage sau batch, hiển thị đủ trạng thái/counters trên card.

Kết quả hồi quy cuối và các checkpoint tiếp theo xem [ROLLBACK_VI](ROLLBACK_VI.md).
