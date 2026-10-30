---
name: soc-cnt
description: Nghiệp vụ CNT — Tối ưu ATTT / Content Security của SABER. Viết rule/chữ ký chạy được (regex, SIEM rule + ATT&CK, YARA, Suricata), tối ưu FP mà không mất TP nghiêm trọng, chẩn đoán nguyên nhân FP, đánh giá độ phủ ATT&CK của intrusion set, trích và phân loại IOC từ TI rồi chuyển thành rule. Phủ 5 NICE task / 15 subtask (T0020 T1406 T1111 T1384 T1644).
---

# CNT — Tối ưu ATTT · Content Security

**Đọc trước:** `.claude/skills/saber-episode-contract/SKILL.md` (nộp bài, chấm, gate) và
`reference/engines.md` (rule chạy trong engine nào, viết sao cho parse được và không timeout).

## Sứ mệnh và SLA (nguồn: `catalog/services.json`)

Xây dựng và tối ưu tập luật giám sát cho SIEM (VCS và 3rd party), **tăng coverage MITRE ATT&CK**, **giảm
FP/Noise**, phát triển parser, **chuyển TI/IR thành rule**.

- Rule/use-case mới: Nghiêm trọng **20h** · Cao **40h** · Trung bình 80h · Thấp 160h.
- Tối ưu FP: rule > 50 alert/8h ⇒ xử lý trong **4h**.
- Rule cho lỗ hổng High/Critical từ TI/IR: **24h (24/7)**.
- Gói Advanced: tối đa 5 use-case/tháng; tối ưu ít nhất 10 rule/tháng; 2 hệ thống/quý cho parser.

## Dòng việc Content Security

```
nguồn đầu vào: log/PCAP/mẫu (HV-02 HV-24 HV-18) · TI/IR (HV-35 HV-34 HV-32 HV-33) · thống kê nhiễu (HV-06 HV-11)
   │
   ├─► viết rule/chữ ký mới ............ T0020 (rule SIEM) · T1406 (YARA, Suricata, parser)
   ├─► tối ưu rule nhiễu ................ T1111 (filter FP, chẩn đoán nguyên nhân, không mất TP nghiêm trọng)
   ├─► đo & lấp độ phủ ATT&CK ............ T1384 (intrusion set → technique chưa phủ → use-case hunting)
   └─► chuyển TI thành chỉ dấu & rule ... T1644 (trích IOC, phân loại độ bền, IOC → rule chạy được)
   ▼
đóng gói theo phiên bản release, quản trị vòng đời rule (HV-05 kho rule + mapping ATT&CK)
```

## Bản đồ task → tài liệu tham chiếu

| NICE | Việc | Subtask | Mode | Đọc |
|---|---|---|---|---|
| T0020 | Xây dựng nội dung (rule/chữ ký) cho công cụ phòng thủ | .001–.003 | file, soc, soc | `reference/rule-authoring.md` |
| T1406 | Xây dựng chữ ký (YARA, Suricata, parser) | .001–.003 | file, file, soc | `reference/rule-authoring.md` |
| T1111 | Quản lý cập nhật rule & chữ ký (tối ưu FP) | .001–.003 | file, file, soc | `reference/rule-tuning.md` |
| T1384 | Quy trình intrusion set (độ phủ, use-case hunting) | .001–.003 | file, file, soc | `reference/coverage-intel.md` |
| T1644 | Xây dựng chỉ dấu tác chiến (IOC → rule) | .001–.003 | file, file, soc | `reference/coverage-intel.md` |

## Nguyên tắc nghề

1. **Rule là sản phẩm chạy được, không phải mô tả.** Điểm đến từ việc engine chạy rule trên corpus/mẫu
   thật — một rule đẹp mà không parse được hoặc timeout là 0.
2. **Bám hành vi bền vững, không bám giá trị đổi được.** Hash, IP, domain đổi trong vài phút; cấu trúc
   payload, chuỗi config, chuỗi tiến trình thì khó đổi (Pyramid of Pain).
3. **Precision là một nửa công việc.** Corpus được chọn có nền "dễ khớp nhầm" — mọi rule phải sống sót
   qua hard negative (từ SQL trong ngữ cảnh lành tính, công cụ quản trị, near-miss string).
4. **Tối ưu FP không được đổi lấy bỏ lọt.** Mất bất kỳ TP mức Nghiêm trọng/Cao nào ⇒ 0.
5. **"Không đủ dữ liệu" khác "không có dấu vết".** Thiếu nguồn log thì use-case không thể chạy — nói rõ.
6. **Không đẩy rule vào SIEM thật, không đẩy vào tập test ẩn.** Content chỉ được đánh giá trên holdout
   đóng băng (`docs/BENCHMARK_PROTOCOL.md` — leakage prevention).

## Trạng thái chấm (trung thực)

15 subtask `VERIFIED_OFFLINE`; 6 bài mode `soc` cần SIEM/NSM/EDR thật ⇒ `BLOCKED_INTEGRATION` ở mức hệ
thống. Exemplar viết tay: T0020.001 (regex). Gold pilot dữ liệu nghiệp vụ: T0020.001, T1406.001
(yara_subset), T1111.002 (filter DSL). Live lab chấm Content Security bằng `T0020.001` trên episode
held-out cùng họ, khác seed (đo **độ bền khi rút lại**, không phải tổng quát hoá khác họ). Ở fixture DEV
tự động mọi `exec/*` chạy bằng engine regex. 0 `READY_BENCHMARK`.
