# Điều tra log đã nhập trong SABER

Bổ sung ngày 2026-11-03, dựa trên các ý tưởng có ích trong `ir.py`: index log, truy vấn
nhiều lượt, giữ tiến độ và rà soát phản ứng. Phần này dùng chung cho world application/native
và controller SOC lab. Nó dùng planner/provider/quota hiện có, không tạo vòng gọi model riêng.

## Chạy demo trên máy hiện tại

Không cần Docker, AD hay API key. Chọn thư mục output mới; script không ghi đè lần chạy cũ.

```powershell
uv run --no-sync python scripts/smoke_forensics.py --out runs/forensics-demo
node agent-office/bin/agent-office.js watch --world runs/forensics-demo --open
```

Chọn **Blue Team → blue-dfir → forensic_query / response_review**. Demo dùng lịch thao tác
scripted, gọi HTTP thật của world và đọc access log tổng hợp. Màn hình hiện bộ lọc,
mẫu bản ghi, ID/hash, nhận định và thiếu sót cần xử lý. `proof.json` ghi kết quả kiểm thử.
Demo kết thúc `PARTIAL`: access log với HTTP 200 chưa đủ chứng minh xâm nhập hoặc phục hồi.

## Nhập log cho Gemini điều tra

```powershell
uv run --no-sync saber world init --out runs/ir-world --clients 1
uv run --no-sync saber world forensics import --out runs/ir-world --file .\logs\edr.csv --format csv --label "EDR export pc-a"
uv run --no-sync saber world forensics sources --out runs/ir-world
```

Trước lần chạy đầu, sửa `goal` của `blue-dfir` trong `runs/ir-world/config.json`, ví dụ:
“Điều tra các log đã nhập: xác định phạm vi, dựng timeline, phân biệt hành vi hợp lệ và đáng ngờ,
dẫn ID bằng chứng, rà thiếu sót phản ứng và lưu kết luận partial khi chưa đủ bằng chứng.”
Giữ nguyên những actor khác nếu muốn client/red/blue tiếp tục công việc thông thường.

```powershell
uv run --no-sync saber world run --out runs/ir-world --ticks 80 --llm --key-pool keys_pool.txt --call-budget 200
node agent-office/bin/agent-office.js watch --world runs/ir-world --open
uv run --no-sync saber world forensics sessions --out runs/ir-world
```

Thay tên file key pool bằng đường dẫn đang dùng; không đưa key vào goal/log. Đây là cấu hình
Gemini hiện có: lựa chọn công cụ do model quyết định, quota dùng chung theo đội. Xem nguồn
`llm`/`scripted-fallback` trên Office. Scripted baseline thông thường không tự điều tra log nhập;
demo phía trên có lịch riêng. World cũ giữ skill đã pin; world mới nhận hướng dẫn vừa cập nhật.

Sau restart, blue nhận danh sách phiên gần đây và dùng `forensic_status` để tiếp tục.
`PARTIAL` có thể tiếp tục nếu còn ngân sách bước; `REVIEWED` chỉ đọc, cần mở phiên follow-up.
Operator đọc toàn bộ lịch sử hoặc kiểm lại bản gốc:

```powershell
uv run --no-sync saber world forensics inspect --out runs/ir-world --session SESSION_ID
uv run --no-sync saber world forensics verify --out runs/ir-world --source SOURCE_ID
uv run --no-sync saber world forensics evidence --out runs/ir-world --id RECORD_ID
uv run --no-sync saber world forensics evidence --out runs/ir-world --id RECORD_ID --export .\record-original.bin
```

`evidence` đối chiếu hash và trả metadata/preview. `--export` ghi nguyên byte bản ghi,
có thể chứa dữ liệu nhạy cảm; chỉ operator có lệnh này và file đích phải chưa tồn tại.

## Định dạng và nguồn bằng chứng

| `--format` | Đầu vào / quy tắc |
|---|---|
| `csv` | CSV UTF-8 có header, hỗ trợ quote và bản ghi nhiều dòng. Các cột chính: Timestamp/UtcTime/TimeCreated, Computer/Hostname, Image/ProcessName, ProcessGuid, ProcessId, ParentImage, ParentProcessId, EventID, CommandLine, SourceIp, DestinationIp. Alias đối chiếu tên chính xác, không dùng substring để nhầm EventRecordID thành EventID |
| `apache` | Access log common/combined, timestamp chứa offset, request/status; dòng không nhận diện được vẫn giữ và báo parse warning |
| `iis` | W3C có dòng `#Fields:` và date/time; thời gian W3C được đọc là UTC |
| `text` | Mỗi dòng là một bản ghi; trích timestamp ISO khi có, phần còn lại tìm theo chuỗi literal |

Timestamp giữ cả giá trị gốc và UTC với microseconds. Timestamp thiếu zone giữ unknown;
operator có thể truyền `--assume-offset +07:00` khi đã biết zone. `UtcTime` khai báo UTC.
Syslog thiếu năm không tự gán năm hiện tại. UTF-16, EVTX, JSON nhiều lớp và CSV dùng dấu chấm phẩy
chưa có parser trực tiếp: export/chuyển đổi có kiểm soát trước, giữ bản nguồn ban đầu để đối chiếu.
Các trường ngoài schema vẫn có trong bản gốc và phần text được index, không tự biến thành trường chuẩn.

File nhập được **sao chép nguyên byte**, SHA-256, tên nguồn, thời điểm nhập, offset/length/hash mỗi bản ghi.
Input không bị sửa/xóa. Bản sao nằm trong `<out>/forensics/<SOURCE_ID>.original`; index và phiên nằm
trong `forensics/index.sqlite3`. Đối chiếu toàn file khi mở/rà/hoàn tất hồ sơ và từng bản ghi khi đọc/dẫn chứng.
Hash chứng minh tính nhất quán với bản lưu, không chứng minh log do nguồn đáng tin tạo ra.

Đây là dữ liệu lịch sử được operator cấp riêng, **không phải event live hoặc ground truth của world**.
ID bản ghi nhập và ID case/event của world/collector thuộc hai không gian khác nhau. Không dùng ID nhập
để gọi containment hoặc đóng case live. Nguồn log chỉ đưa cho blue; mỗi phiên thuộc actor tạo nó.
Muốn đồng đội kiểm lại, `share` nguồn, câu hỏi, bộ lọc và trích dẫn; bên nhận mở phiên riêng rồi đọc lại.

## Công cụ và trạng thái

| Công cụ | Cách dùng |
|---|---|
| `forensic_sources` | Danh sách nguồn, 10/trang; `after` tiếp tục. Không nhận đường dẫn từ agent |
| `forensic_open` | `source_ids` (1–8) và `question`; chờ ID phiên trả về |
| `forensic_query` | `session_id`, `mode`: search/timeline/stats/process; text literal, host, process_guid, pid, ip, since/until, group_by, limit, after |
| `forensic_record` | `category`: scope/observation/hypothesis/containment/eradication/recovery; `text`, `evidence_ids` đã đọc trong phiên |
| `forensic_status` | Xem checkpoint: 4 bước và 5 findings gần nhất; operator `inspect` đọc lịch sử đầy đủ |
| `response_review` | DFIR/IR/lead/recovery: nhập `residual_risk`, nhận gaps về phạm vi/cô lập/loại bỏ/khôi phục, thiếu query hoặc coverage |
| `forensic_finish` | `disposition` reviewed/partial + `summary`; reviewed cần review hiện hành không còn gap; query/finding mới làm review cũ mất hiệu lực |

Pivot process cần **host + ProcessGuid**, hoặc **host + PID + since/until có timezone**.
PID vẫn có thể tái sử dụng trong khoảng thời gian đó. Không ghép tất cả process cùng tên thành một tiến trình.
Timeline loại timestamp unknown và báo điều này; stats tính trên dữ liệu đã index, chỉ trả top groups.
Search phân biệt với regex: ký tự `(a+)+$` được tìm nguyên văn, không được thực thi như biểu thức.
`ip` lọc SourceIp/ClientIP; DestinationIp có trong fields, có thể tìm literal trong text.

Chu trình chuẩn là đọc → truy vấn → chờ kết quả → ghi nhận định dẫn chứng → rà gaps → lưu kết luận.
Công cụ kiểm citation có tồn tại/đã đọc và hash đúng; **chưa kiểm ngữ nghĩa nhận định**.
`REVIEWED` nghĩa là hồ sơ được rà, `response_verified` luôn false trong các công cụ này.
Không có phản ứng nào được tự thực thi, không có case nào tự đóng. Kiểm phản ứng thật vẫn qua
collector/SOAR và `verify_recovery` của runtime tương ứng.

## Dung lượng, quyền và giới hạn

- Không load toàn bộ file vào RAM: index streaming vào SQLite. Giới hạn 128 MiB/file,
  200.000 bản ghi/file, 128 KiB/bản ghi vật lý hoặc logic, tối đa 100 nguồn và 256 phiên/thư mục.
  Admission budget của vault 512 MiB, SQLite derivatives tối đa 384 MiB; cần chừa chỗ cho WAL/tệp tạm.
  Khi đầy, dừng báo lỗi; không tự xóa bằng chứng. Dùng thư mục điều tra mới cho đợt khác.
- Index text tối đa 16.384 ký tự/bản ghi; raw vẫn đầy đủ. Parse lỗi, vượt ngưỡng hoặc mất timestamp
  có warning. `indexed_complete=false` khi dừng giữa file; không gọi kết quả rỗng là “không có tấn công”.
- Query tối đa 20 bản ghi và khoảng 16 KB preview, có thể trả ít hơn rồi `next_after` tiếp tục.
  Giữ cùng filter khi phân trang. Mỗi query có ngân sách SQL 3 giây; thu hẹp phạm vi khi hết thời gian.
- Mỗi phiên tối đa 200 bước, còn quyền lưu kết luận partial ở ngưỡng đó; không tự báo hoàn thành vì hết lượt.
  Range lưu receipt theo job để replay pending không tạo phiên/finding trùng. Tối đa 10.000 receipt/thư mục.
- Office giữ 12 thao tác điều tra/actor; world xuất tối đa 20 preview trong cửa sổ 200 event toàn world.
  Mỗi preview tối đa 3 bản ghi mẫu/20 ID/8 KB. SQLite giữ lịch sử phiên tới giới hạn nêu trên.
  Khi snapshot gần 250 KB, Office bỏ bớt preview cũ để vẫn xem đủ roster/event; hiện thông báo để operator dùng inspect/evidence.
- Preview được che một số mẫu credential phổ biến; đây không phải bộ DLP hoàn chỉnh. Bản gốc vẫn chứa
  nội dung nguyên vẹn. Operator chỉ nhập dữ liệu được phép cho blue/provider đang cấu hình đọc.
  Bảo vệ/backup thư mục `forensics` cùng data directory; không sửa `.original` hoặc index bằng tay.

## Dùng với SOC lab trên máy lớn

`saber lab forensics` có cùng các lệnh, nhưng `--out` phải là **data directory của controller**,
không phải thư mục bundle. Với Compose đã chạy từ bundle build bằng code mới:

```powershell
docker compose -f runs/soc-bundle/compose.yaml cp .\logs\edr.csv controller:/tmp/edr.csv
docker compose -f runs/soc-bundle/compose.yaml exec -T controller saber lab forensics import --out /data --file /tmp/edr.csv --format csv --label "Authorized EDR export"
docker compose -f runs/soc-bundle/compose.yaml exec -T controller saber lab forensics sessions --out /data
```

Controller thực hiện phân tích cục bộ; không tạo PID worker hay giả receipt OS. Không cần thêm service,
cài `ir.py` hoặc dependency của ứng dụng gốc. Các source/phiên tồn tại trong volume controller qua restart.
Các lệnh Compose này là hướng dẫn triển khai; máy hiện tại chưa chạy kiểm chứng Docker/AD đầy đủ.

## Kiểm thử và phần chưa đưa vào

Test parser, quyền, citation, hash, giới hạn, restart và luồng planner có tại `tests/forensics`,
`tests/world/test_forensics.py`, `tests/lab/test_forensics.py`. Provider fixture kiểm luồng nhiều lượt,
không phải đo chất lượng nhận định Gemini thật. Smoke HTTP và Chrome có script riêng trong repo.
Receipt local: `runs/forensics-final-demo-20261103/proof.json` và `ui/verification.json`.

Kết quả local ngày 2026-11-03:

| Kiểm tra | Kết quả |
|---|---|
| Toàn repo, bật Chrome thật | **1.468 passed**, 7 subtests passed; `runs/forensics-full-tests-final.xml` |
| Sau các sửa cuối về ID/date, export và snapshot 200 agents | **29 passed**; `runs/forensics-focused-tests-final.xml` |
| Hồi quy skill consultation + parser | **28 passed**; `runs/forensics-regression-tests.xml` |
| Office | **17 Node tests passed**; Chrome kiểm query/hash/gaps/HTML escaping, không lỗi JavaScript |
| Ruff / format / mypy | PASS; mypy cả Linux và Windows, 206 modules |
| Skill audit | PASS, 18 definitions / 15 operational / 56 references; `runs/forensics-skills-check.json` |

Lượt full đầu phát hiện thiếu chỗ cho bài học mới trong prompt DFIR; đã rút gọn phần contract
chung bị lặp, giữ giới hạn context và nội dung nghiệp vụ. Receipt lỗi ban đầu vẫn giữ ở
`runs/forensics-full-tests.xml`; lượt full sau và test hồi quy đã đạt. Các kết quả trên là local,
không phải xác nhận GitHub CI, Gemini judgment hoặc nghiệm thu Docker/AD.

Chưa đưa Word export/attack-map của `ir.py` vào vì các hàm đó phụ thuộc module ngoài không có trong repo.
Không mang theo logic xóa file đầu vào, fuzzy column mapping, bỏ timezone, tự gắn “verified” bằng model,
hay coi HTTP 2xx/3xx là exploit thành công. `ir.py` gốc được giữ nguyên, không import hay chạy wrapper API.
