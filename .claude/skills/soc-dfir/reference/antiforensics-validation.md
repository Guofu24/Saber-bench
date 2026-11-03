# DFIR · Dấu vết bị can thiệp, kiểm giả thuyết và độ tin cậy

Chọn khi nghi log clear/tamper, timestomp, masquerading, deleted data hoặc nguồn telemetry không đáng tin.
Mục tiêu là đánh giá điều còn chứng minh được; không dựng lại dữ liệu đã mất bằng suy đoán.

## Kiểm theo giả thuyết đối lập

| Dấu hiệu | Nguồn kiểm tiếp | Giải thích khác cần loại trừ |
|---|---|---|
| Log đứt quãng | Sensor heartbeat/collector offsets, rotation/retention, audit changes, central copy | Reboot/outage, forwarding error, quyền đọc, hết lưu trữ |
| Security 1102 / log clear | Actor/session, remote copy, change record, activity trước/sau | Admin bảo trì; event không mô tả mọi record đã bị xóa |
| Timestamp bất thường | MFT SI/FN/USN, process/file telemetry, package/deploy dates, backup/version | Copy/extract/restore/timezone/tool semantics; chênh SI/FN không tự là timestomp |
| File bị xóa | Journal/metadata/deleted entries, snapshot/backup, EDR file history | Rotation/update/temp cleanup; carving thiếu path/time/owner |
| Process/module bị “ẩn” | Memory cross-view, image compatibility, independent endpoint/network log | Race, exited process, unloaded module, symbol/parser mismatch |
| Cùng IOC nhiều máy | Exact hash/path/time và distribution/change system | Software rollout, shared cache, backup/quarantine scans |
| Hash sau chuyển khác | Source/transfer manifests, encoding/redaction/decompression và byte counts | Derived format khác legitimate; vẫn phải tách lineage, không thay hash cho khớp |

Timestomp có thể tác động nhiều timestamp; đừng dùng một cặp timestamp như phép thử chắc chắn phát hiện mọi lần.
Giữ original bytes và timestamps, ghi correction riêng. ATT&CK là vocabulary để mô tả hành vi có căn cứ,
không là bằng chứng actor hoặc hướng dẫn thực hiện anti-forensics.

## Kiểm nguồn và công cụ

1. Ghi chain nguồn: sensor/device → forwarder → collector → SIEM → export/parser → finding.
   Hai downstream bản sao cùng nguồn không là corroboration độc lập. Xác định mắt xích nghi bị can thiệp.
2. Kiểm parser với dữ liệu đã biết: đúng version/schema/locale, positive và benign near-match,
   truncated/corrupt/missing fields. Failed parse khác zero findings.
3. Kiểm thủ công record then chốt trên raw bytes/structured fields hoặc parser độc lập phù hợp.
   Hai tools dùng cùng parser backend không hoàn toàn độc lập; ghi dependency.
4. Time normalization giữ source time/offset/precision/uncertainty; không nội suy sự kiện trong khoảng mất log.
5. Negative evidence chỉ có trọng lượng nếu nguồn đáng lẽ ghi hành vi, policy đang bật, sensor khỏe,
   retention đủ, query đúng quyền/phạm vi và không cắt trang. Ghi điều kiện đó trong finding.

## Mẫu finding khi nghi tamper

```text
Observed anomaly: raw record/field/byte reference
Tamper hypothesis / benign alternatives
Independent sources checked / unavailable
Integrity and coverage limitations
What can still be concluded / what cannot be reconstructed
Confidence rationale / next collection or review owner
```

Đừng chờ chứng minh tamper hoàn toàn mới báo ongoing risk; cũng không gán “attacker xóa dấu vết” cho mọi gap.
Peer review tập trung assertion có thể bị bác bỏ bằng dữ liệu nào. Công cụ, analyst và automated lesson đều
có thể sai; giữ revision/correction trail, không xóa kết luận trước khỏi hồ sơ để báo cáo trông nhất quán.

Nguồn: [MITRE T1070.006](https://attack.mitre.org/techniques/T1070/006/),
[SWGDE Examination 2.0](https://www.swgde.org/documents/published-complete-listing/18-f-001-2/).
