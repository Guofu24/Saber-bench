# Skills: phạm vi, cách nạp và kiểm tra

Repo có **11 skills** trong `.claude/skills`: **8 sổ tay nghiệp vụ** cho agent và
**3 workflow phát triển**. Có **25 tài liệu tham chiếu** được liên kết từ các skills
nghiệp vụ. Skill là hướng dẫn cho model; quyền thực thi do runtime/tool server kiểm
soát, không do nội dung Markdown cấp.

## Vai nào dùng skill nào

| Vai | Skill |
|---|---|
| Client, mọi vai người dùng | `client-user` |
| Red recon / access | `redteam-initial-access` |
| Red impact | `redteam-post-exploitation` |
| Blue monitor | `soc-mon` |
| Blue hunter | `soc-hunt` |
| Blue DFIR / IR | `soc-ir` — runtime cấp hai bộ tool khác nhau |
| Blue content | `soc-cnt` |
| Blue lead | `soc-orchestrator` |

`implement-task`, `implement-benchmark-subtask`, `gate-review` phục vụ phát triển và
review repo; không nạp vào prompt của client/red/blue. Hai workflow `implement-task`
và `gate-review` giữ `disable-model-invocation: true`: đây là trường hợp lệ của
[Claude Code](https://code.claude.com/docs/en/skills#control-who-invokes-a-skill).
Validator dành riêng cho định dạng Codex có thể không nhận trường này; không xóa
chính sách gọi skill chỉ để làm validator khác hệ thống báo xanh.

## Hai chế độ nạp

Loader chung là `src/saber/agents/skills.py`. Population, benchmark specialist và
continuous world đều dùng loader này, với ngữ cảnh khác nhau:

| Chế độ | Nội dung model nhận | Giới hạn |
|---|---|---|
| `case` — population / benchmark B2 | Body `SKILL.md` và nội dung các tài liệu được tham chiếu, đi theo liên kết, loại trùng; bỏ hướng dẫn riêng của world | 64.000 ký tự |
| `world` — continuous world có model | Body theo vai và hợp đồng application lab dùng chung | 18.000 ký tự |

World không có filesystem tool để model tự mở file tham chiếu. Loader đưa trực tiếp
[hợp đồng world](../.claude/skills/soc-orchestrator/reference/continuous-world.md)
vào prompt, giải thích rõ role/tool, thông báo người dùng, bằng chứng và phạm vi hiệu
ứng ứng dụng. Hướng dẫn enterprise/OS không được coi là công cụ đã tích hợp. Phần
`observation.tools` và JSON contract của runtime quyết định hành động hợp lệ.

Case nhận tài liệu nghiệp vụ đầy đủ hơn nên input token có thể tăng so với bản cũ
chỉ nạp entrypoint. Giới hạn tính bằng **ký tự**, không phải token. Vượt giới hạn,
thiếu file, sai frontmatter, tham chiếu thoát phạm vi hoặc symlink sẽ báo lỗi rõ;
không cắt đuôi hướng dẫn hay tự đổi specialist thành generic. B1 vẫn là generic theo
thiết kế. Lỗi skill lúc khởi động world có model được phát hiện trước khi mở HTTP
lab/khởi chạy planner. File được đọc lại khi tạo prompt, không giữ cache cũ suốt process.

Scripted world dùng policy Python và không gọi model, nên skill không quyết định
hành động của scripted agent. Các test offline có thể kiểm tra nạp prompt và quyền
tool; chúng không chứng minh model hiểu hoặc làm theo skill một cách đáng tin cậy.

## Bundle local / sandbox / VM / remote

`env render` xuất 8 entrypoint và toàn bộ tài liệu tham chiếu nghiệp vụ được khai
báo, theo đường dẫn tương đối. Hash được ghi vào manifest. File Markdown không được
tham chiếu, workflow phát triển, key pool và dữ liệu run không được tự động đóng gói.
Thiếu tài liệu bắt buộc thì export thất bại thay vì sinh bundle thiếu chuyên môn.

Bundle là bản chụp source lúc render. Sửa skill trong checkout không cập nhật một
container/bundle đang dùng bản cũ; cần export/rebuild theo quy trình môi trường.
Bundle mới có Compose project/volume mới: không tự chuyển dữ liệu world cũ.

## Một lệnh kiểm tra

Từ root repo:

```powershell
uv run python scripts/check_skills.py --out runs/skills-check/audit.json
```

Lệnh kiểm tra frontmatter của 11 skills, các file tham chiếu, tài liệu nghiệp vụ bị
bỏ rơi, giới hạn ngữ cảnh, coverage role → skill và chính sách manual-only hiện tại.
Không đọc key pool, gọi provider, chạy hành động red/blue hay thay đổi dịch vụ ngoài.
CI chạy cùng lệnh kiểm tra này trước các kiểm tra code.

Kiểm thử phần nạp prompt, xuất bundle và runtime:

```powershell
uv run pytest tests/unit/test_skills.py tests/unit/test_llm_solver.py tests/world tests/population tests/environments
uv run ruff check src tests scripts
uv run ruff format --check src tests
uv run mypy
uv run python scripts/validate_catalog.py
```

## Kết quả kiểm tra ngày 2026-11-01

- Đã sửa: reference không được đưa vào prompt case; bundle bỏ sót reference;
  thiếu skill bị thay bằng chuỗi rỗng; tham chiếu chéo không tương đối đúng;
  `red/access` nạp nhầm giai đoạn; một số chỉ dẫn chưa phân biệt world với enterprise.
- Audit: **PASS — 11 skills, 8 nghiệp vụ, 25 reference**, không có reference bị bỏ rơi.
- Các test nêu trên, lint, format, typecheck và frozen catalog đều qua.
- Smoke bằng source export: **15 actor, 13 vai, 8 skills, 4 tick, 54 request HTTP
  loopback**, 15 hành động được chọn qua planner giả. Không gọi API bên ngoài.
- Artifact local: `runs/skills-final-check/audit.json` và
  `runs/skills-final-check/portable-verification.json` (không đưa dữ liệu run vào Git).

Phạm vi xác nhận là cấu trúc, nạp prompt, role/tool và khả năng chạy từ source export.
Chưa phải đo chất lượng suy luận Gemini, test tích hợp SIEM/Ghidra/IDA thật, hay bằng
chứng Docker/VM đã được triển khai. Trạng thái vẫn là `DEV_SIMULATION_ONLY`.
