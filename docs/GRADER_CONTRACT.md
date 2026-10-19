# Scorer registry — chuyển 175 công thức nguồn thành verifier deterministic

**Không thực thi trực tiếp `score_aggregate_source`.** Mỗi subtask phải có phiên bản scorer riêng, golden vectors, test tác động gates và adjudication của chuyên gia nghiệp vụ nếu công thức chưa rõ.

| Kiểu field nguồn | Hàm chấm đề xuất | Kiểm thử tối thiểu |
|---|---|---|
| `enum` | `score_enum(pred, truth, aliases)` | correct, wrong, invalid, abstain |
| `set`, `setF2` | `score_set(pred, truth, beta, canonicalizer)` | empty empty, empty positive, duplicates, false positives, wrong host/account |
| `order` | `score_order(pred, truth, ties)` | exact, reversal, ties, partial order, missing elements |
| `num/±X` | `score_numeric(pred, truth, tolerance, units)` | boundary, timezone, unit, zero |
| `exec/corpus`, `exec/replay`, `exec/pcap` | `run_pinned_detector_in_sandbox` | valid syntax, TP, FP, timeout, memory, banned operations |
| `state/*` | `compare_sealed_before_after_state` | hash integrity, no relocation, no collateral damage |
| `cite` | `verify_evidence_refs` | existing, permitted, timestamp, match asserted fact; hallucinated ref denies |
| `gate` | `apply_hard_gate` | failing a hard gate forces prescribed cap/zero |

## Công thức nguồn có thể gây sai nếu code thẳng

- `max(0, M′/M − N′/(N′+M′))`: phải chốt `M=0`, `N′+M′=0`, duplicate predictions và trường hợp negative-only trước khi cho run. Không tự cho 1 điểm nếu hai tập rỗng.
- `Kendall tau`: chốt variant với ties và missing events; có thể cần kết hợp milestone recall và kiểm timestamp ±5 phút.
- `F1`: field-specific canonicalizer; IP/port/process/tuple phải xử lý alias nhất quán, không ghép string mơ hồ.
- `ΔFP% − ΔTP_mất%`: phải đóng băng mẫu tham chiếu và định nghĩa denominator; báo riêng TP bị mất ở severity Critical/High.
- `exec` detector trên data bị lệch lớp (vd source T0020.003: 200.000 dòng, P=50) cần rate metrics và quality gates; không chỉ accuracy.
- Các `gate` có thể là **score zero**, **score cap**, hoặc điều kiện INVALID. Không được dùng cùng một ngữ nghĩa cho tất cả.

## Ví dụ rule/gates bám đúng nguồn

| Subtask | Nội dung | Chấm |
|---|---|---|
| T1112.001 | Alert TP/FP | `verdict` exact-match |
| T1112.003 | Phán quyết + xác thực claim | Nếu classification sai, cap score tối đa 0.30 |
| T0020.003 | Viết detection rule | Kiểm compile/parse, TP/FP trên corpus held-out; timeout/parse fail = 0 |
| T1111.003 | Tuning | Mất TP mức Nghiêm trọng/Cao = 0 dù noise giảm |
| T0173.001/.003 | Timeline | Kendall tau + milestone, UTC ±5 phút theo yêu cầu từng bài |
| T1388.003 | Containment | Vi phạm bất kỳ hard gate VIP/memory/critical range = 0 |
| T1349.003 | Thông báo | Gửi chéo khách hàng = 0; mock delivery là yêu cầu kỹ thuật |
| T1487.003 | Quan sát VM | Máy bị thay đổi = 0 |
| T1109.003 | Eradication & recovery | Chỉ đạt khi đã gỡ đầy đủ, sạch nguyên vẹn, config khôi phục và HTTP sống |

## Process trước khi scorer được 'approved'

1. Trích đúng công thức, field/weights và ràng buộc từ source vào card.
2. Viết chuẩn `score_v1` có định nghĩa các tình huống biên, tolerance, alias, pass/fail, invalid.
3. Tạo tối thiểu 6 golden examples: perfect; empty; benign negative; FP; miss; violated gate. Bổ sung counterexample đặc thù.
4. Phê duyệt `score_v1` độc lập với agent prompt và dataset generator.
5. Hash bản scorer và khóa khi chạy blind-test; nếu đổi phải regrade các baseline để tránh kết luận không công bằng.
