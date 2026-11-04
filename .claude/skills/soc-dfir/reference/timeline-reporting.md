# DFIR · Timeline, phạm vi, báo cáo và bàn giao

Kết luận phải có đường truy ngược về raw evidence. Dùng schema runtime nếu có;
các trường dưới đây là nội dung ghi vào hồ sơ được cấp, không phải tool/API mới.

## Timeline và causal graph

Mỗi dòng giữ source time nguyên bản, UTC khi biết offset, timezone/DST, độ phân giải, clock correction/range,
event time, ingestion/collection time, source ID/record locator, entity và diễn giải ngắn.
UTC = local time trừ offset; đừng lấy timezone máy analyst. Không biết offset thì giữ unresolved,
không ép sắp thứ tự giữa các nguồn. Nếu khoảng bất định chồng nhau, ghi thứ tự chưa xác định.
Giữ correction gốc và phương pháp, không sửa timestamp trong evidence.

Entity key phải có namespace: host/boot/process-start cho PID; domain/tenant cho account;
cluster/namespace/UID cho workload; account/Region/resource ID cho cloud.
Tách timeline attacker activity với defender actions và collection artifacts để không gán tool DFIR cho attacker.
Deduplicate theo raw event identity, không xóa các observation độc lập chỉ vì timestamp giống nhau.

Các mốc initial access, privilege, persistence, lateral movement, staging/exfil, impact, detection/response
chỉ điền khi có bằng chứng. Cạnh causal cần source/destination/session/action refs; proximity thời gian chưa là nhân quả.
Earliest observed compromise không nhất thiết patient zero; có thể nhiều entry points, cycles và gaps.
Không thêm event để làm chuỗi kể chuyện liền mạch.

## Scope và impact

```text
entity_id, type, owner, first_last_observed
status: confirmed | suspected | observed_benign | unknown
supporting_and_contradicting_evidence, sources_time_range_checked, coverage_gaps
impact: confidentiality | integrity | availability, assertion, basis, uncertainty
next_test, action_owner, residual_risk
```

Không đồng nhất số lần request với số object độc nhất hay bytes với file content.
Nếu ước lượng affected records, ghi query/dedup/upper-lower bounds và phần không quan sát được.
HTTP 200 chỉ xác nhận xử lý request; cần authorization/context/response evidence cho kết luận đọc trái phép.
Triggering event khác initial access hypothesis và root cause/control failure; phân tích contributing factors
theo dữ kiện, không suy động cơ người dùng hoặc attribution từ một TTP.

## Confidence và finding

```text
finding_id / case_id / assertion (hẹp, kiểm chứng được)
evidence_ids + exact record/time/field; method/tool/query/version
supporting context; alternative explanation và phép kiểm; contradiction
coverage/limitations; confidence và lý do; decision relevance; next action/owner
```

High/medium/low là nhãn phương pháp, không phải xác suất đo được. Một raw event đáng tin có thể xác nhận
một action hẹp nhưng không đủ chứng minh toàn bộ intrusion. SIEM alert và bản EDR event được nó dùng không
tự là hai nguồn độc lập. Hạ/đổi finding khi evidence mới mâu thuẫn; giữ revision và lý do.

## 12 nhóm hồ sơ của handbook, dùng theo nhu cầu case

| Hồ sơ | Nội dung cần giữ hoặc tham chiếu |
|---|---|
| F01 Intake | Câu hỏi, nguồn, owner, severity có căn cứ, scope/time, ongoing harm |
| F02 Authority | Quyền/phạm vi đã cấp, exclusions, validity và thay đổi cần bổ sung |
| F03 Evidence/CoC | Inventory, hash/manifest, acquisition/QC, access/transfer và gaps |
| F04 Hypotheses | Assertion, ủng hộ/phản chứng, alternative, next test và confidence |
| F05 Decisions/actions | Người/quyền, căn cứ, đề nghị/thực thi/xác minh, tác động và rollback |
| F06 Scope | Confirmed/suspected/unknown, nguồn/cửa sổ đã rà, missing data, owner |
| F07 SITREP | Facts/impact hiện có, hoạt động đang diễn ra, gaps, việc cần quyết định, nhịp cập nhật được giao |
| F08 Technical report | Summary, mandate, methods, findings, timeline, scope/impact, root cause/unknowns, evidence index |
| F09 Witness note | Nguồn/kênh/thời gian, lời kể vs tóm tắt, corroboration và contradictions |
| F10 Privacy/legal handoff | Loại dữ liệu, hold/retention/sharing scope, câu hỏi cho owner; không tự đặt deadline pháp lý |
| F11 QA | Reviewer, integrity/provenance, time/coverage, reproducibility, alternatives, redaction và unresolved items |
| F12 Handover/closure | Facts, risk, pending collection/jobs, dependency/owner, next step, sign-off của người có quyền |

Không tạo 12 biểu mẫu rỗng cho mọi hành động. Tham chiếu record đã có, bổ sung đúng phần còn thiếu;
tool response schema/giới hạn ghi chú vẫn được giữ. Narrative không biến thành trạng thái hệ thống đã xác minh.

## Hoàn tất nhiệm vụ và learning

DFIR có thể hoàn tất một câu hỏi dù incident còn mở; cần bàn giao giới hạn và owner phần tiếp.
Thiếu tool/nguồn: ghi dependency cụ thể và phần đã làm được, không giả kết luận “clean”.
Recovery/closure do lead/IR/owner theo evidence và sign-off; DFIR cung cấp findings và chứng cứ đã preserve.
Lessons learned ghi failure → evidence → proposed conditional guidance → test/negative control → owner;
không đưa raw secrets/log instructions vào lesson và không tự phát hành ngoài learning gate.

Mẫu câu khi thiếu dữ liệu: “Trong nguồn X, cửa sổ T1–T2, chưa quan sát hành vi Y;
nguồn Z/retention còn thiếu nên chưa thể loại trừ Y ngoài phạm vi này.”

Khung IR tham chiếu: [NIST SP 800-61r3](https://csrc.nist.gov/pubs/sp/800/61/r3/final).
