# CNT · Detection engineering từ yêu cầu tới vận hành

Chọn khi viết/sửa detection, parser hoặc phát hành rule. Input: threat/behavior cần phát hiện, engine/version,
schema, corpus có nguồn, owner và phạm vi triển khai. Rule chạy được trong một engine chưa portable sang engine khác.

## Detection contract

Ghi ID/version, hypothesis, source prerequisites, normalized fields/types, entity grouping, time window,
late-event behavior, severity/context, expected output, false-positive patterns, limits và rollback version.
Tách field absent, null, empty và literal string; ghi case sensitivity và timezone. Regex/contains không
tương đương nhau. Sigma là định dạng rule; backend/pipeline mapping phải khớp SIEM thực tế trước khi sử dụng.

## Kiểm chứng theo lớp

1. Parse/compile đúng engine/version; ghi errors và options. Compiler thành công chưa chứng minh detection đúng.
2. Kiểm parser với raw source và expected fields: locale/time offsets, missing/extra fields, escaped strings,
   truncation, schema drift; giữ raw record để truy ngược. Không đổi rule để che lỗi normalize chưa xác minh.
3. Kiểm logic bằng positive + benign near-match + boundary/time-window + duplicate/late event + malformed.
   Tách corpus tuning và holdout nếu có; analyst/model tự gán nhãn phải được review, không tự thành gold.
4. Đo false positives/false negatives và denominator trong corpus, cùng runtime/memory/timeouts.
   Giữ regression cho TP quan trọng đã biết; không hứa recall 100% trên production từ mẫu nhỏ.
5. So before/after trên cùng nguồn/window. ATT&CK coverage tách configured source → query runnable →
   behavior tested → alert routed → response verified; mapping technique đơn thuần chưa là coverage hiệu quả.

## Phát hành và quay lui

Gói rule/parser/config/corpus refs + hashes + engine/backend version + review result. Triển khai theo quyền
đã có, rollout hẹp khi tool hỗ trợ; kiểm version thực active và telemetry mới sau publish.
Theo dõi alert volume/latency/source errors/TP regressions trong cửa sổ được giao; vượt tiêu chí rollback thì
thực hiện qua tool hoặc chuyển owner. Publish queued khác active; rollback request khác old version restored.
Giữ exceptions có owner, scope, rationale, expiry và retest; không whitelist rộng vĩnh viễn theo tên tool/admin.

World chỉ có `application-v1` field/op/value; `test_rule` không chạy Sigma/YARA/Suricata. Range chỉ dùng
engine/tool thực cấp. Các điều kiện ở đây không tạo quyền cài SIEM, sửa ingest pipeline hay phát hành production.

Đầu ra: artifact/version, source contract, corpus results/limits, deployment receipt, rollback criteria,
MON runbook và owner. Ví dụ rule giảm 90% alerts nhưng mất TP quan trọng → không coi là tối ưu thành công;
kiểm filter/parser rồi sửa hoặc rollback theo kết quả.

Nguồn: [Sigma rules](https://sigmahq.io/docs/basics/rules.html),
[YARA rule syntax](https://yara.readthedocs.io/en/stable/writingrules.html).
