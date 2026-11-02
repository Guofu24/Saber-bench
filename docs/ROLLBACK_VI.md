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
