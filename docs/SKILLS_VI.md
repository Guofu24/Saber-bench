# Skills: phạm vi, cách nạp và kiểm tra

Repo có **18 skills** trong `.claude/skills`: **15 sổ tay nghiệp vụ** cho agent và
**3 workflow phát triển**. Có **56 tài liệu tham chiếu** trong audit nghiệp vụ, gồm
contract world/range và 13 reference DFIR. Skill là hướng dẫn cho model; quyền thực thi do runtime/tool server kiểm
soát, không do nội dung Markdown cấp.

Rà cấu trúc không đủ để xác nhận nghiệp vụ. [Báo cáo rà nội dung](SKILLS_REVIEW_VI.md) đối chiếu yêu cầu client/red/blue
và 55 nhóm NICE / 175 subtask, ghi các suy luận sai đã sửa, quy trình phối hợp còn thiếu đã bổ sung, cùng những
khả năng runtime/model chưa kiểm chứng. Không coi audit PASS là SOC đã hoàn chỉnh.
Đợt mở rộng tiếp theo bổ sung [12 chuyên môn blue và công cụ runtime](SOC_SPECIALISTS_VI.md),
gồm task có nhận việc, chứng cứ, notebook, vòng đời actor, rule và phục hồi.
Đợt mới nhất đã rà nguồn và bổ sung toàn bộ 15 skill nghiệp vụ; xem [coverage từng vai](ALL_SKILLS_COVERAGE_VI.md).

## Vai nào dùng skill nào

| Vai | Skill |
|---|---|
| Client, mọi vai người dùng | `client-user` |
| Red recon / access | `redteam-initial-access` |
| Red impact | `redteam-post-exploitation` |
| Blue monitor | `soc-mon` |
| Blue hunter | `soc-hunt` |
| Blue DFIR | `soc-dfir` |
| Blue IR | `soc-ir` |
| Blue content | `soc-cnt` |
| Blue lead | `soc-orchestrator` |
| Blue malware / reverse engineering | `soc-malware` |
| Blue network | `soc-network` |
| Blue threat intelligence | `soc-intel` |
| Blue SOC platform | `soc-platform` |
| Blue identity | `soc-identity` |
| Blue recovery | `soc-recovery` |

`implement-task`, `implement-benchmark-subtask`, `gate-review` phục vụ phát triển và
review repo; không nạp vào prompt của client/red/blue. Hai workflow `implement-task`
và `gate-review` giữ `disable-model-invocation: true`: đây là trường hợp lệ của
[Claude Code](https://code.claude.com/docs/en/skills#control-who-invokes-a-skill).
Validator dành riêng cho định dạng Codex có thể không nhận trường này; không xóa
chính sách gọi skill chỉ để làm validator khác hệ thống báo xanh.

## Ba chế độ nạp

Loader chung là `src/saber/agents/skills.py`. Population, benchmark specialist,
continuous world và SOC lab đều dùng loader này, với ngữ cảnh khác nhau:

| Chế độ | Nội dung model nhận | Giới hạn |
|---|---|---|
| `case` — population / benchmark B2 | Body `SKILL.md` và nội dung các tài liệu được tham chiếu, đi theo liên kết, loại trùng; bỏ hướng dẫn riêng của world | 64.000 ký tự |
| `world` — continuous world có model | Body theo vai, hợp đồng application lab; mỗi đội tra cứu reference bằng `consult_skill` | Base 18.000 ký tự |
| `range` — SOC lab | Body theo vai, hợp đồng executor/collector/analysis/SOAR; mỗi đội tra cứu reference bằng `consult_skill` | Base 18.000 ký tự |

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
lab/khởi chạy planner. Loader trực tiếp/case vẫn đọc source; continuous world chụp bản
gốc và giữ epoch bền qua restart, thay vì đổi prompt giữa case khi file source thay đổi.
World nạp skill theo `active_specialty` của task đã nhận, trong tập chuyên môn operator
đã cấu hình cho actor; task/message không thể tự cấp thêm skill hoặc quyền tool.
Phần [agent learning](AGENT_LEARNING_VI.md) thêm bài học có kiểm thử vào phiên bản skill
cục bộ, giữ history/rollback. Release mới đợi epoch không còn case/task đang mở.

Scripted world dùng policy Python và không gọi model, nên skill không quyết định
hành động của scripted agent. Các test offline có thể kiểm tra nạp prompt và quyền
tool; chúng không chứng minh model hiểu hoặc làm theo skill một cách đáng tin cậy.

## Bundle local / sandbox / VM / remote

`env render` xuất 15 entrypoint và toàn bộ tài liệu tham chiếu nghiệp vụ được khai
báo; `lab render` bổ sung contract range. Các đường dẫn giữ tương đối, hash được ghi vào manifest. File Markdown không được
tham chiếu, workflow phát triển, key pool và dữ liệu run không được tự động đóng gói.
Thiếu tài liệu bắt buộc thì export thất bại thay vì sinh bundle thiếu chuyên môn.

Bundle là bản chụp source lúc render. Sửa skill trong checkout không cập nhật một
container/bundle đang dùng bản cũ; cần export/rebuild theo quy trình môi trường.
Bundle mới có Compose project/volume mới: không tự chuyển dữ liệu world cũ.

## DFIR: handbook và đối chiếu nguồn chính thức

[Review handbook](DFIR_HANDBOOK_REVIEW_VI.md) ghi lỗi xác nhận được, nguồn đối chiếu và phần không thể
suy thành năng lực thực thi. [Skill DFIR](../.claude/skills/soc-dfir/SKILL.md) có luồng nhận case →
giả thuyết → thu/QC → phân tích → scope/impact → handoff → learning.
[Bảng năng lực DFIR](DFIR_CAPABILITY_COVERAGE_VI.md) ghi câu hỏi/đầu ra theo nghiệp vụ, nguồn nghiên cứu
và mức kiểm chứng. Mười ba reference gồm:

| Reference | Nội dung |
|---|---|
| `acquisition` | Chọn phương pháp, volatility/risk, manifest/hash/custody, xử lý partial/mismatch |
| `host-forensics` | Windows/Linux/macOS, execution/session/persistence, artifact caveats |
| `memory-malware` | Symbols/plugin, injection alternatives, static/dynamic boundary và analysis receipts |
| `network-identity` | DNS/PCAP/flow/email, AD/Entra, session/token/grant và impact |
| `cloud-containers` | AWS/Azure/GCP/SaaS/Kubernetes/CI-CD; phạm vi OT/mobile/appliance |
| `timeline-reporting` | Time uncertainty, entity graph, confidence, 12 nhóm hồ sơ và bàn giao |
| `incident-playbooks` | 12 tình huống, dữ liệu cần thu, giả thuyết đối lập và tiêu chí kết luận |
| `queries-validation` | Query tái lập, pagination, parser/negative controls và tiêu chí đánh giá hành vi |
| `disk-filesystems` | Partition/sector offset, TSK, deleted/carved data, filesystem caveats, Plaso |
| `remote-collection` | Collection plan, Velociraptor/offline collector, resource caps, partial/completion proof |
| `windows-ad-investigation` | Session/process graph, AD objects, audit/SACL, trust scope, Defender KQL |
| `cloud-query-recipes` | AWS CLI, Entra KQL, GCP filter với schema/time/entity/pagination cụ thể |
| `antiforensics-validation` | Tamper/timestomp/log gaps, corroboration, parser validation và negative evidence |

`case` nạp cả 13 reference. `world`/`range` nhận bản cốt lõi, contract và danh mục topic của skill active.
Blue gọi `consult_skill` với `{"topic":"memory-malware"}` (ví dụ); lần suy luận tiếp theo nhận toàn văn
hướng dẫn đó. `{}` liệt kê, `{"topic":""}` bỏ chọn. Mỗi lần chọn một tài liệu, tối đa 12.000 ký tự,
index tối đa 5.000; không nạp cả thư viện vào mọi request. Base/lessons vẫn có trần 18.000 riêng.
Scripted policy không tự đổi hành vi khi sửa Markdown.

Library lấy từ file đã khai báo thuộc skill đó và tài liệu dùng chung cùng đội, hash từng nội dung và nằm
trong immutable skill version. Topic dùng chung có tiền tố owner, ví dụ `soc-ir--malware-analysis`;
client/red cũng được consult nhưng không có quyền đọc hướng dẫn/case state của blue qua tool này.
Restart, lesson release và rollback giữ đúng library; selection của version/specialty cũ không được áp sang bản khác.
Model không cung cấp đường dẫn/file/URL; văn bản chèn trong observation không thay được nội dung library.
World ghi receipt tra cứu; range xử lý tại controller và đánh dấu `guidance_only`, không giả PID hay evidence thu máy.

World đang chạy giữ epoch/skill version đã chụp; cập nhật source không thay prompt giữa case.
Muốn thử baseline mới, tạo world/bundle mới; với learning release dùng quy trình activation/rollback hiện có.
Bundle đã render cần render/rebuild lại để mang theo skill mới. Không chép skill đè vào bundle có manifest hash.

## Một lệnh kiểm tra

Từ root repo:

```powershell
uv run python scripts/check_skills.py --out runs/skills-check/audit.json
```

Lệnh kiểm tra frontmatter của 18 skills, các file tham chiếu, tài liệu nghiệp vụ bị
bỏ rơi, giới hạn ngữ cảnh, coverage role → skill và chính sách manual-only hiện tại.
Không đọc key pool, gọi provider, chạy hành động red/blue hay thay đổi dịch vụ ngoài.
CI chạy cùng lệnh kiểm tra này trước các kiểm tra code.

Kiểm thử phần nạp prompt, xuất bundle và runtime:

```powershell
uv run pytest tests/unit tests/world tests/lab tests/population tests/environments
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts
uv run mypy
uv run python scripts/validate_catalog.py
```

## Kiểm tra và lịch sử

Kết quả bản mở rộng hiện tại và lệnh tái lập nằm trong [SOC_SPECIALISTS_VI](SOC_SPECIALISTS_VI.md).
Các số dưới đây thuộc checkpoint cũ trước khi bổ sung 7 skill; giữ để đối chiếu lịch sử:

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
