# Source-of-truth: phạm vi 175 SOC benchmark subtasks

**Đây là dữ liệu người dùng cung cấp, không phải một bản thiết kế suy đoán từ framework chung.** Source snapshot được giữ ở `source/nice_coverage_4dichvu_SOC_subtask.html`; SHA256 `92b53fad8d20909381875c70c8b0d9d198273256d0d2ff86b617c74c68080d6b`. Parser chỉ trích dữ liệu JSON trong JavaScript; không chạy code HTML/JS. Các trường `scenario_source`, `score_items_source`, `score_aggregate_source` và `source_review` giữ nguyên nội dung gốc.

| Dịch vụ chính | NICE tasks | Subtasks | File | SOC | VM |
|---|---:|---:|---:|---:|---:|
| MON | 16 | 58 | 30 | 25 | 3 |
| CNT | 5 | 15 | 9 | 6 | 0 |
| HUNT | 13 | 39 | 25 | 6 | 8 |
| IR | 21 | 63 | 46 | 10 | 7 |
| **Tổng** | **55** | **175** | **110** | **47** | **18** |

## 3 tầng định danh, không được đánh đồng

- **Engineering task T001–T038** trong `tasks/BACKLOG.md`: những PR phát triển phần mềm, hạ tầng và evaluator. Chúng **không phải** 55 NICE tasks hay 175 benchmark subtasks.
- **NICE task T####**: mô tả năng lực nghiệp vụ SOC trong file nguồn. Có 55 mục sau review; 9 mục đã loại lưu ở `catalog/dropped_nice_tasks.json` và không được tự ý tái đưa vào phạm vi.
- **Benchmark subtask T####.NNN**: đơn vị chấm điểm độc lập. 175 bản ghi, gồm một subtask có thể có input HV, output và metric riêng, như T1112.001 vs T1112.003.

## Giải thích môi trường (diễn giải triển khai)

- `file` — người làm nhận artifact/file có thể chạy scorer độc lập. **Không có nghĩa chỉ hỏi đáp**, vì rule/YARA có thể cần thực thi kiểm thử offline.
- `soc` — tích hợp nguồn dữ liệu/công cụ SOC, có thể cần stateful SOAR sandbox. Không tự cho rằng `soc` luôn là VM thật hoặc luôn phải tác động hệ thống.
- `vm` — cần VM/snapshot và verifier trạng thái; kiểm soát hành động đọc/ghi, hash file sạch và ảnh hưởng dịch vụ.

## 40 lớp hiện vật (HV)

`catalog/artifacts.json` giữ định nghĩa gốc của HV-01…HV-40. Một số trọng tâm:

| Artifact | Vai trò |
|---|---|
| HV-01 / HV-02 | Alert nguồn và log thô, tách signal vs evidence |
| HV-07 / HV-08 / HV-10 | Case, phán quyết, worklog và vòng đời SLA |
| HV-05 / HV-06 | Rule repository / thống kê rule, rule execution |
| HV-15 / HV-16 / HV-18 | Process telemetry, registry/service/task, hashes |
| HV-20 / HV-24 / HV-26 / HV-27 | Memory, PCAP, Windows/AD, Firewall/Proxy/VPN |
| HV-37…HV-40 | Network, asset, severity/SOP và internal whitelist |

## Những phần còn thiếu (không được tự coi đã có)

- HTML chứa **đặc tả**, không chứa đầy đủ dataset, binary, disk image, raw PCAP, ground-truth sealed, credentials, snapshot image, API của sản phẩm SOC hoặc tất cả 175 verifier.
- 170/175 subtask có trường `n` bằng chuỗi `"0"`; 5 mã có `n` khác 0 nhưng **không chứng minh** đã đạt quality gate. Không dùng `n` làm nhãn DONE.
- 106 subtask ghi output `*tự sinh khi dựng bài*` (nguồn chưa định nghĩa artifact đầu ra cụ thể). Các phần này phải có schema trước khi code.
- Các biểu thức chấm điểm trong HTML là mô tả toán học; chưa được chuyển thành thuật toán đúng về zero-division, empty-set, alias, ngưỡng, ties, hard-gates và invalid episodes.
- Các yêu cầu live SIEM/EDR/VCS product được giữ là dependency; fake adapter không đồng nghĩa chứng minh integration thật.

## Trình tự nguồn ưu tiên

1. Dữ liệu thực trong `catalog/subtasks.json` và mỗi `tasks/subtasks/T####.NNN.md`.
2. Điều kiện môi trường & evidence ở `docs/SUBTASK_CONTRACT.md` và `docs/GRADER_CONTRACT.md` (chỉ là đề xuất implement, phải giữ nguyên nghĩa nguồn).
3. Điều phối triển khai ở `docs/IMPLEMENTATION_SEQUENCE.md`.
4. `tasks/BACKLOG.md` cho engineering-only dependencies.

**Không được** chỉnh sửa yêu cầu nghiệp vụ gốc để vừa với code hiện có; nếu phát hiện xung đột thì báo yêu cầu adjudication và lưu ADR.
