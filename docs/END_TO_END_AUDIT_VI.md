# Rà soát xuyên suốt SABER — 2026-11-02

Phạm vi: cấu hình triển khai, 15 skill nghiệp vụ, quyền và việc nạp hướng dẫn,
runtime world/range, learning, bằng chứng/Office, CI và hướng dẫn vận hành.
Đây là kiểm chứng code và lab local; chưa nghiệm thu toàn bộ Docker/Windows AD
hoặc đo chất lượng quyết định Gemini trên bộ dữ liệu độc lập.

## Các vấn đề đã sửa

| Vấn đề tìm thấy | Thay đổi | Bằng chứng |
|---|---|---|
| Office mô tả `consult_skill` như job có log process đã kiểm hash | Hiển thị tra cứu tại controller; không nhận `evidence_complete` cho thao tác này, không tìm process evidence không tồn tại; đọc được cả export cũ | Test Python cho cả ba đội, test Node và Chrome với receipt thành công/thất bại |
| Learning replay vẫn nhận analysis/SOAR đã tắt trong cấu hình | Replay và live planner dùng chung tập công cụ theo deployment; prompt và bộ chấm cùng lọc | Candidate bị từ chối khi suite cũ yêu cầu `analyze_sample` hoặc `run_playbook` đã tắt |
| Lab Linux vẫn quảng bá `contain_domain_user` | Loại công cụ AD khỏi planner/replay và health menu khi không có Windows; worker từ chối trước dispatch | Test replay AD và HTTP 403, không sinh process event |
| CI chưa chạy bộ test Office, có thể bỏ sót HTML build cũ | Thêm job Node trên Linux/Windows, test protocol/UI selectors và build so với bản đã commit | 16 test Node và build local qua; workflow được kiểm tra cú pháp. Chưa suy ra GitHub CI đã xanh |
| Smoke dựa vào lần đọc tiếp theo của red trong 12 tick và kiểm tra sau khi TTL có thể đã hết | Quan sát phản ứng đã xác minh, gửi phép thử HTTP trong lúc phản ứng còn hiệu lực; red phải bị chặn và client vẫn đọc được, kèm evidence ID | Giữ nguyên hai receipt thất bại ban đầu; chạy lại proof có phép thử trực tiếp |
| Tài liệu thiết kế ban đầu dễ bị hiểu là kiến trúc đang chạy | Bổ sung bản đồ implementation world/env/lab/benchmark; cập nhật README, notes, Office và learning | Kiểm tra các đường dẫn tài liệu nội bộ và lệnh đối chiếu code |

Các bản vá được chia commit: `af66dc4` (Office), `d0aab14` (CI),
`7a27611` (capability/replay), `19db465` (smoke); tài liệu có commit riêng tiếp theo.

## Kết quả kiểm tra

| Kiểm tra | Kết quả / artifact local |
|---|---|
| Toàn bộ pytest, có Chrome thật | **1.449 passed**, 0 failed/error/skip; `runs/final-polish-tests.xml` |
| Regression sau sửa capability, replay và guidance | **14 passed, 1 skipped**; `runs/final-polish-lab-regression.xml`. Test Chrome bỏ qua ở lượt con do chưa đặt biến môi trường; đã chạy đạt trong lượt toàn repo |
| Ruff và format | PASS trên `src tests scripts` |
| mypy Linux và Windows | PASS, 201 source modules |
| Skill audit | PASS: **18 definitions, 15 operational skills, 56 reference files**; `runs/final-polish-skills.json` |
| Frozen catalog và DEV smoke | PASS: 55 NICE tasks / 175 subtasks / 40 HV artifact types; `T1112.001`, seed 42 |
| Ba preset SOC | Manifest và Compose parse PASS cho `linux-small`, `windows-ad`, `expanded`, cả scripted/Gemini, kiểm tra lại với source sau sửa; `runs/final-polish-bundles-current/validation.receipt.json` |
| Office Node/build | **16 passed**; build khớp `viewer/index.html` đã commit |
| Chrome với bằng chứng range | PASS trên proof mới: ba đội, lọc job, log process, ảnh đúng hash, receipt guidance và không lỗi JavaScript; `runs/final-polish-loopback-v3/ui/verification.json` |
| Loopback mới | **PASS**, 6 agent / 12 tick: có phản ứng SOAR được xác minh, red HTTP 403, client HTTP 200, native YARA và ảnh Chromium; `runs/final-polish-loopback-v3/proof.json` |
| PowerShell | Parse PASS cho 12 script được Git theo dõi; không chạy provision |
| Liên kết tài liệu | README/notes/Office và toàn bộ `docs/*.md`: không có relative Markdown link trỏ tới file thiếu |

Lượt toàn repo là kiểm tra nền; các lượt regression kiểm tra code sau sửa.
Các artifact dưới `runs/` nằm trên máy kiểm thử, được gitignore; máy mới cần chạy lại.
Không gọi provider hoặc đọc pool Gemini thật trong đợt rà soát này.

## Chạy lại trên máy khác

Tại root repo, dùng môi trường đã cài dependency theo lockfile. Nếu cần khởi tạo mới,
`uv sync --locked --extra analysis`; Office chỉ cần `npm --prefix agent-office ci`
khi chưa có dependency build. Không cần Docker/VM cho test offline.

```powershell
uv run pytest --junitxml=runs/quality-tests.xml
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts
uv run mypy --platform linux
uv run mypy --platform win32
uv run python scripts/validate_catalog.py
uv run python scripts/check_skills.py --out runs/skills-audit.json
npm --prefix agent-office test
npm --prefix agent-office run build:viewer
git diff --exit-code -- agent-office/viewer/index.html
```

Để bật test Chrome, đặt `SABER_TEST_CHROME` tới executable Chromium/Chrome đã cài
và bảo đảm môi trường có Playwright. Proof loopback cần cả Playwright và dependency
analysis; không mở Docker hoặc Hyper-V:

```powershell
# Chỉ khi môi trường chưa có Playwright; dùng phiên bản đã pin cho SOC lab
uv pip install --python .venv/Scripts/python.exe playwright==1.56.0
$env:SABER_TEST_CHROME = 'C:\Program Files\Google\Chrome\Application\chrome.exe'
uv run --no-sync python scripts/smoke_soc_loopback.py --out runs/new-local-proof --chrome $env:SABER_TEST_CHROME --ticks 12
node agent-office/bin/agent-office.js watch --world runs/new-local-proof/controller --open
```

Đường dẫn output proof phải mới. Script tạo credential lab dùng một lần trong
`.secrets`, không lấy credential từ pool người dùng. Phép thử bổ sung được ghi riêng
trong `response_probes`; không tính chúng là quyết định của model hay action của agent.
Các phản ứng TTL có thể đã hết hạn khi mở lại snapshot đã dừng.

## Những phần còn cần nghiệm thu riêng

- **Máy đích:** build/boot đủ dịch vụ, kiểm tra isolation và `lab verify`; thử backup/
  restore, mất kết nối và retention lâu dài. Compose parse chưa chứng minh các việc này.
- **Windows/AD:** guest thực, Sysmon/Security, relay, phản ứng tài khoản và rollback;
  kiểm tra cùng bộ VM trên host đủ RAM theo [runbook](SOC_LAB_VI.md).
- **Công cụ ngoài:** Ghidra, IDA với license phù hợp, memory image/symbol hợp lệ,
  PCAP và instance SOAR ngoài phải chạy nghiệm thu trong môi trường đích.
- **Chất lượng agent:** benchmark Gemini có budget rõ, nhiều case và benign controls,
  đáp án độc lập, đánh giá sai sót/collateral damage. Test nạp skill hoặc provider
  fixture không chứng minh năng lực điều tra thực tế của model.

Bộ skill đủ các vai trò đã khai báo, với tham chiếu và contract được kiểm tra.
Phạm vi chuyên môn/nguồn ở [bảng coverage](ALL_SKILLS_COVERAGE_VI.md).
Không có kết luận `READY_BENCHMARK` từ đợt rà soát này.
