# Đánh giá handbook và áp dụng cho skill DFIR

Ngày đối chiếu: 02/11/2026. Đầu vào: `DFIR_Handbook_Chuyen_Sau_2026.docx`, phiên bản 1.0,
28 chương, 12 playbook, 12 mẫu biểu. Đọc nội dung và hyperlink trực tiếp từ DOCX;
không sửa hoặc đưa file gốc vào git. Bản review này phân biệt lỗi xác nhận được với phần cần triển khai thêm.

## Kết luận

Tài liệu phù hợp làm khung nghiệp vụ DFIR cho doanh nghiệp và làm nguồn thiết kế skill.
Các điểm tốt: tách observation/inference, không đồng nhất thiếu log với không có xâm nhập,
bảo toàn nguồn gốc bằng chứng, ưu tiên thu theo tình huống, scoping đa nền tảng và phân quyền DFIR/IR.
Đây chưa phải SOP có thể chạy nguyên xi, cũng không chứng minh agent có đủ công cụ hoặc năng lực điều tra.
Không gán phần trăm chính xác khi chưa đánh giá từng quy trình trên dữ liệu thực tế.

Đã đối chiếu các khẳng định kỹ thuật trọng yếu bên dưới với nguồn chính thức. Đây không phải xác nhận
toàn bộ 27 tài liệu tham khảo, mọi plugin, mọi câu lệnh, tính chấp nhận pháp lý hay mọi phiên bản nền tảng.

## Các điểm cần sửa hoặc làm rõ trong handbook

| Vị trí | Kết quả đối chiếu | Cách áp dụng vào skill |
|---|---|---|
| §26.7 AWS CLI | `lookup-events` không có `--max-results` trong CLI hiện hành. Có `--page-size`, `--max-items`, `--starting-token`. `MaxResults` là trường ở cấp API. | Dùng `--page-size 50`; nếu giới hạn tổng bằng `--max-items` thì ghi export chưa đầy đủ và giữ token để tiếp tục. [AWS CLI](https://docs.aws.amazon.com/cli/latest/reference/cloudtrail/lookup-events.html). |
| §11.3 Volatility | Cụm “profile/symbol compatibility” dễ trộn V2 với V3. V3 đã bỏ profiles, dùng layers và symbol tables. | Ghi OS/kernel/build, symbol table, phiên bản/plugin và lỗi; phân biệt trường `profile` của adapter SABER với profile V2. [Volatility 2 → 3](https://volatility3.readthedocs.io/en/stable/vol2to3.html). |
| R04 SWGDE | Tháng 06/2025 là mốc draft public comment. Trang chính thức ghi bản 2.0 ngày 20/11/2025, được duyệt 18/11/2025. | Sửa ngày và trạng thái nguồn khi ban hành SOP. [SWGDE 18-F-002-2.0](https://www.swgde.org/documents/published-complete-listing/18-f-002-2-0/). |
| §6.4 confidence | “High = ít nhất hai nguồn” đã được ghi là thang nội bộ, nhưng không nên biến thành quy tắc cứng cho agent. | Đánh giá tính trực tiếp, toàn vẹn, phạm vi và giải thích đối lập. Hai bản sao cùng một event không phải hai nguồn độc lập; một nguồn có thể xác nhận một khẳng định hẹp. Đây là điều chỉnh phương pháp cho SABER. |
| §26.1 truy vấn Windows | `Select-Object -First 100` tạo một cửa sổ kết quả; câu lệnh không giới hạn thời điểm kết thúc. | Đặt cả start/end, ghi thứ tự và số bản ghi bị giới hạn; không coi 100 kết quả là toàn bộ lịch sử. |
| §17.1 timeline | UTC có ích nhưng dữ liệu thiếu offset/DST hoặc clock skew không cho phép tự tạo thứ tự tuyệt đối. | Giữ giờ gốc, nguồn đồng hồ, độ phân giải và khoảng bất định; tách event/ingest/collection time. |

Lệnh trong DOCX có xuống dòng thật bằng phần tử Word `w:br`. Nếu trích xuất chỉ nối các `w:t`,
PowerShell/Linux/Volatility sẽ trông như bị dính lệnh; đó là lỗi trích xuất, không phải lỗi file gốc.

Ví dụ sửa §26.7, cú pháp **Bash** cho operator đã được cấp quyền; chưa chạy trên tài khoản AWS:

```bash
aws cloudtrail lookup-events \
  --region ap-southeast-1 \
  --start-time 2026-11-01T00:00:00Z \
  --end-time 2026-11-02T00:00:00Z \
  --page-size 50 --output json --no-cli-pager > cloudtrail-events.json
```

CLI tự phân trang khi không tắt pagination; giới hạn account/Region, quyền và loại event vẫn còn.
Chạy trong kho evidence được cấp quyền, giữ raw export, hash, query và lỗi. Không đưa raw export lên prompt.

## Những khẳng định trọng yếu đã xác nhận

| Nội dung | Kết quả và nguồn |
|---|---|
| NIST 800-61r3 | Phát hành 04/2025, thay Rev.2 và gắn IR với CSF 2.0. [NIST](https://csrc.nist.gov/pubs/sp/800/61/r3/final). |
| NICE v2.2.0 | Có thông báo chính thức ngày 28/04/2026; ma trận junior/senior trong handbook vẫn là đề xuất riêng. [NIST NICE](https://www.nist.gov/news-events/news/2026/04/nice-releases-nice-framework-components-v220). |
| SANS Windows Playbook | Trang chính thức ghi 31/03/2026. Đã xác nhận metadata/tóm tắt công khai, chưa tải PDF cần đăng nhập. [SANS](https://www.sans.org/posters/windows-forensic-analysis-playbook). |
| Live acquisition | Thứ tự tùy tình huống; thu live có thể đổi timestamp, gây bất ổn và memory smear. [SWGDE Acquisition 2.1](https://www.swgde.org/documents/published-complete-listing/17-f-002-2-1/). |
| CloudTrail Event History | 90 ngày management events theo account/Region; không thay data events hay tổ chức log đa account. [AWS](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/view-cloudtrail-events.html). |
| GCP Audit Logs | Admin Activity luôn ghi; Data Access mặc định tắt trừ BigQuery, quyền xem cũng khác. [Google Cloud](https://docs.cloud.google.com/logging/docs/audit). |
| Sysmon | Có cấu hình/filter riêng; network event 3 và image-load event 7 mặc định tắt. [Microsoft](https://learn.microsoft.com/en-us/sysinternals/downloads/sysmon). |
| Kubernetes audit | Policy quyết định nội dung và backend giữ log; Metadata không có request/response body. [Kubernetes](https://kubernetes.io/docs/tasks/debug/debug-cluster/audit/). |
| CSIRT service catalog | Framework mô tả dịch vụ/chức năng, không tự cấp quyền thực thi cho analyst. [FIRST v2.1](https://www.first.org/standards/frameworks/csirts/csirt_services_framework_v2.1). |

## Những gì skill cũ cần chỉnh

Skill `soc-dfir` cũ chủ yếu hướng dẫn lấy case, snapshot và timeline. Tài liệu IR dùng chung có các câu
“không cô lập trước thu RAM”, “thiếu checklist thì bằng chứng không dùng được”, “hầu hết công cụ bỏ sót WMI”
quá rộng khi áp vào thực tế. Sửa thành quyết định theo rủi ro, ghi thiếu sót và kiểm nguồn/coverage.
Yêu cầu acquisition order/checklist của một case benchmark cụ thể vẫn phải được tuân thủ; không sửa catalog
hay đáp án để làm benchmark dễ hơn.

## Ánh xạ nội dung cần có trong skill

| Handbook | Hướng dẫn nghiệp vụ cho agent |
|---|---|
| 1–6 | Nhận case, authority hiện có, câu hỏi, severity/ongoing harm, giả thuyết đối lập và collection plan |
| 7–8 | Acquisition theo rủi ro, manifest/hash/custody, bản gốc/bản làm việc, QC và dữ liệu thiếu |
| 9–10 | Windows/Linux/macOS: nguồn artifact, pivots và giới hạn suy luận |
| 11, 16 | Memory và malware: tương thích công cụ, tính toàn vẹn, dấu hiệu so với bằng chứng thực thi |
| 12–15 | Network/email/identity/cloud/Kubernetes; OT/mobile/appliance chuyển đúng chuyên gia/phạm vi |
| 17–18 | Timeline, entity scope, impact, root cause và bàn giao phản ứng/phục hồi |
| 19 | 12 thẻ tình huống, nguồn cần tìm, giả thuyết đối lập và điều kiện kết luận |
| 20–24 | Chọn công cụ có thật, kiểm chứng coverage, QA và điều kiện hoàn tất nhiệm vụ |
| 25–28 | Mẫu hồ sơ gọn, truy vấn tái lập được, nguồn tham chiếu và lưu hạn chế |

RACI tuyển dụng, maturity, kế hoạch 90 ngày, pháp lý và SLA là cấu hình vận hành của tổ chức;
không chuyển thành quyền mới, thời hạn pháp lý mặc định hay checklist bắt buộc trên mọi hành động của agent.

## Ranh giới thực thi

- `world/application` và `world/native`: case/log/snapshot ứng dụng; native chỉ đo workload cố định,
  không phải thu disk image/RAM hoặc EDR toàn máy.
- `lab/range`: dùng các tool controller cấp, export/timeline, Windows collection khi đã có guest,
  và phân tích sample đã đăng ký khi engine/symbol/license tương ứng sẵn sàng.
- Cloud, macOS, mobile, OT và Kubernetes trong handbook là hướng dẫn điều tra dữ liệu được cung cấp;
  thêm skill không tự triển khai connector, acquisition driver, parser hay quyền production.
- Chỉ trạng thái hoàn tất cùng receipt/evidence mới chứng minh thực thi; queued/failed/unavailable khác clean.
- Kiểm tra cấu trúc/prompt không phải kiểm thử chất lượng suy luận của Gemini. Cần case hợp lệ và
  golden datasets/negative controls để đánh giá từng domain trước khi tuyên bố năng lực đầy đủ.

## Kết quả triển khai và kiểm tra

Đã mở rộng [soc-dfir](../.claude/skills/soc-dfir/SKILL.md) với 8 reference chuyên sâu,
12 thẻ tình huống và 12 nhóm hồ sơ; thêm quy trình xử lý hash mismatch, partial acquisition,
clock uncertainty, thiếu audit/data access, benign alternatives và job chưa hoàn tất.
Đã cập nhật README và [hướng dẫn nạp skill](SKILLS_VI.md); giữ nguyên API/tool permissions và catalog.

| Kiểm tra offline | Kết quả |
|---|---|
| Skill frontmatter và validator repository | PASS: 18 skills, 15 nghiệp vụ, 34 reference; không tài liệu bị bỏ rơi |
| Prompt DFIR `case` | 56.297 / 64.000 ký tự, gồm reference đầy đủ |
| Prompt DFIR `world` / `range` | 17.041 / 12.031 ký tự, mỗi mode dưới trần 18.000 |
| Tests skill/solver/specialties/bundle/deployment/learning | 59 passed, không failure/error/skip |
| Ruff lint / format | PASS; 305 file đã đúng format |
| Mypy Linux / Windows | PASS; 200 source files mỗi nền tảng |
| Frozen catalog | PASS: 55 nhóm NICE, 175 subtasks; không đổi đáp án |
| Ví dụ PowerShell mới | Parse syntax PASS, không thực thi thu dữ liệu trên máy |

Artifact local: `runs/dfir-handbook-review/skills-expanded.json` và
`runs/dfir-handbook-review/tests.xml`. Không gọi provider, không đọc key pool,
không triển khai cloud/VM hoặc chạy acquisition thật trong đợt sửa skill này.
Các ca hành vi ở reference `queries-validation` là tiêu chí đánh giá tiếp theo, không phải kết quả Gemini đã đạt.
