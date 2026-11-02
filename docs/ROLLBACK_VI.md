# Commit, kiểm tra và rollback

## Lịch sử triển khai environment profiles

Các checkpoint trên branch `feat/environment-profiles`:

| Commit | Thay đổi |
|---|---|
| `dd52a62` | Profile/schema và CLI chọn, tạo, validate cấu hình |
| `d78ab9e` | Bundle portable, Compose và kiểm tra nội dung export |
| `e8bd92c` | Lifecycle local/guest/container, report, STOP/resume |
| `5a38514` | Doctor và health check chỉ đọc cho dịch vụ được khai báo |
| `ab4bbe5` | Resume dùng một lần và chặn file ngoài manifest trong build context |
| `4ef4087` | README và hướng dẫn các môi trường, checkpoint rollback |
| `fb1f693` | Snapshot world cho office, counter runtime, không xuất dữ liệu riêng |
| `51dbb37` | Watch local/sandbox, validate snapshot và SSE replay |
| `c3e475d` | UI world, lọc đội, phân trang, quota và kiểm thử trình duyệt |
| `2367ee0` | Đóng gói viewer độc lập cho local/VM/server và host sandbox |
| `f46c633` | Hướng dẫn theo dõi runtime bằng viewer và rollback |
| `c03694b` | Làm rõ khả năng world trong skills, sửa tham chiếu chéo và hướng dẫn nghiệp vụ |
| `cd76fcc` | Loader skill có kiểm tra, export đầy đủ reference và audit trong CI |
| `960d9a0` | Ghi kết quả audit cấu trúc và hợp đồng nạp skills |
| `4d4479b` | Sửa suy luận SOC thiếu căn cứ, chuẩn hoá IOC và ngữ cảnh pháp y |
| `ca0f898` | Quy trình client/red/blue qua nhiều lượt, bàn giao và kiểm chứng rule/parser |
| `32cfddd` | Báo cáo rà nội dung theo yêu cầu và 55 nhóm NICE / 175 subtask |
| `c49a109` | Query phân trang/cutoff, case evidence/finding có revision, đóng FP và mở lại |
| `9cabb54` | 12 chuyên môn blue, 7 skill mới và actor kiêm nhiệm có kiểm quyền |
| `2997ba4` | Task có nhận việc/bàn giao, notebook bền, wait/finish/resume và vô hiệu plan cũ |
| `dafe196` | Artifact có hash, builtin analysis, test/version/rollback rule, telemetry/recovery |
| `2786a5f` | Yêu cầu đánh giá lại kết luận khi case có chứng cứ mới |
| `266219f` | Office hiện chuyên môn/task/lifecycle; baseline dùng chuyên môn đang nhận việc |
| `a268bc1` | Kiểm HTTP đầu cuối SOC/client recovery, smoke 12 chuyên môn và hướng dẫn phối hợp |
| `f12c211` | Hướng dẫn dùng 12 chuyên môn, kiểm chứng và rollback |
| `38384cb` | Nhật ký trải nghiệm riêng, skill version bất biến và epoch tồn tại qua restart |
| `7c67814` | Worker reflection dùng chung quota, replay gate và phát hành lesson |
| `4cc90a1` | Đổi epoch vô hiệu hóa kế hoạch cũ, giữ trạng thái WAITING/DONE |
| `729546f` | Snapshot notebook khi đóng episode, chặn note viết muộn cùng tick |
| `cb1db65` | CLI inspect/export/retry/rollback, suite mẫu, learning-only và office counters |
| `5ef203d` | Báo cáo usage sau learning batch và tránh cắt mất counters trên UI |
| `646c1aa` | Hướng dẫn luồng học, replay gate và vòng đời phiên bản |
| `2fa2123` | Harness Gemini thật có budget, lập kế hoạch/reflection/replay và log chỉ có metadata |
| `725740d` | Probe replay có nguồn operator, giữ nguyên NO_LESSON và budget tích lũy |
| `ef33025` | Notes tra nhanh các lệnh vận hành client/red/blue |
| `8b20bc4` | Trace thao tác có giới hạn và phản ứng case đã lọc cho Agent Office |
| `008576a` | Bấm robot/màn hình/thẻ để xem thao tác, mục tiêu và phản ứng phòng thủ |
| `3fbf4fd` | Định nghĩa ba khu, kiểm tra 72 chỗ ngồi và phân trang theo từng đội |
| `ed3aaf3` | Cảnh office ba khu riêng, chọn 36/72 slots và camera nhìn từng khu |
| `9e59031` | Native executor, process/file/DNS/TCP thật, lịch sử và phân trang CLI |
| `23944f7` | Agent Office xem native theo actor/event, kiểm thử Chrome và lỗi sau thực thi |

Các commit tài liệu/kiểm thử tiếp theo xem bằng:

```powershell
git log --oneline --decorate -15
git show --stat COMMIT
git diff COMMIT_TRUOC COMMIT_SAU
```

Mỗi commit gồm một thay đổi chức năng hoặc sửa lỗi có mục đích rõ. Commit cuối là
bản nên dùng; các checkpoint giữa chừng có thể chưa chứa toàn bộ lệnh/documentation.

## Hoàn tác thay đổi code

Với lịch sử đã chia sẻ, tạo commit hoàn tác để giữ dấu vết:

```powershell
git status --short
git revert COMMIT_CAN_HOAN_TAC
```

Các thay đổi có phụ thuộc nhau; khi hoàn tác nhiều commit, làm từ mới về cũ và kiểm
tra conflict/test. Không dùng `reset --hard` để tránh xóa thay đổi chưa commit.

Để xem/chạy một phiên bản cũ mà giữ nguyên checkout đang làm:

```powershell
git worktree add --detach ../Saber-bench-review COMMIT_CAN_XEM
```

Chạy `uv sync --locked` và kiểm thử trong worktree đó. Không dùng chung thư mục world
đang hoạt động giữa hai phiên bản/process. Bản trước feature này là `28c7e63`.

## Hoàn tác môi trường/dữ liệu

1. Dừng world bằng `world stop`, hoặc `env down` cho container.
2. Giữ bản sao world/named volume đã dừng. Copy cả dữ liệu, không chỉ `report.json`.
3. Chọn code/bundle đã kiểm thử cùng phiên bản dữ liệu; khôi phục vào môi trường riêng.
4. Kiểm tra report, world ID, case, log và budget trước khi tiếp tục.

`env down` giữ named volume. Tránh `docker compose down -v` trừ khi chủ động muốn xóa
dữ liệu. VM snapshot được quản lý ở hypervisor. Git revert không tự đổi container
đang chạy, không revert database và không phục hồi quota Google đã dùng. Nếu restore
database cũ, counters cục bộ cũng có thể lùi: phải đối chiếu usage thực của nhà cung cấp
và giữ bản counters mới nhất trước khi bật lại Gemini.

Bản mở rộng SOC lưu thêm task, notebook, artifact, rule version và actor-control trong
world database. Code trước mở rộng không hiểu các trạng thái này; không dùng nó để tiếp
tục world có actor WAITING/DONE hay task đang mở. Giữ bản sao dữ liệu đã dừng và thử bản
cũ trên world riêng. Revert code không tự hoàn tác một rule, response hoặc task đã chạy.

Phần học lưu thêm journal/episode, proposal, suite, evaluation, skill version/release và
epoch. `world learning rollback` đổi release head cho epoch tiếp theo, không sửa lịch sử
và không đổi pin của case đang mở. Git revert không rollback các bản skill lưu trong DB.
Xem [AGENT_LEARNING_VI](AGENT_LEARNING_VI.md) để phân biệt rollback code, dữ liệu và skill.

Native mode bổ sung `execution_mode` trong config/checkpoint, bảng `native_events`,
log xuất và thư mục `workloads/`, `native-office/`. Code trước `9e59031` không hiểu
config native. Muốn quay lại application mode hãy dùng world mới hoặc bản sao world
application đã dừng; không xóa trường config để ép resume checkpoint native. Revert
viewer không xóa bằng chứng, nhưng viewer cũ sẽ không hiện cửa sổ native.
