# CNT · Tối ưu rule nhiễu — T1111 (quản lý cập nhật rule & chữ ký)

Quản trị cập nhật rule/signature cho SIEM: cập nhật định kỳ tháng/quý dựa trên kết quả IR và cảnh báo
mức Cao/Nghiêm trọng từ VCS TI; đóng gói theo phiên bản; quản trị vòng đời. Gói Advanced: **tối ưu ít
nhất 10 rule mỗi tháng**. Task mang tag MON + IR + CNT (rule nhiễu ảnh hưởng thẳng ca trực).

| Subtask | Mode | Đầu vào | Phải nộp | Chấm |
|---|---|---|---|---|
| **T1111.001** | file | HV-06 (1 rule, N alert, M là FP) | điều kiện lọc (`rule`/`filter`) | `max(0, ΔFP% − ΔTP_mất%)` — verifier áp lại lên log |
| **T1111.002** | file | HV-06, HV-11 | filter + `fp_cause` | 0.7 filter + 0.3 enum |
| **T1111.003** | soc (SIEM) | HV-01 04 05 06 11 35 37 | filter | `max(0, ΔFP% − ΔTP_mất%) × [không mất TP Nghiêm trọng/Cao]` — gate `no_critical_tp_lost` |

**Đọc công thức:** điểm = (% FP bị loại) − (% TP bị mất). Ví dụ trong đề: **giảm FP 80% mà mất 10% TP
được 0.70**. Ở .003 mất **bất kỳ** TP mức Nghiêm trọng/Cao nào ⇒ **0**.

## Quy trình tối ưu một rule nhiễu

1. **Gom FP theo đặc điểm chung** (HV-06): cùng tiến trình cha, cùng tài khoản dịch vụ, cùng host/nhóm
   host, cùng khung giờ, cùng đường dẫn/tham số. Tìm 1–3 cụm giải thích phần lớn FP.
2. **Đặt từng cụm cạnh các TP**: điều kiện lọc phải **đúng cho FP và sai cho mọi TP**. Nếu TP cũng có
   đặc điểm đó (vd "đọc nhiều file" — ransomware thật cũng vậy), thêm điều kiện thứ hai thu hẹp (tiến
   trình hợp lệ + tài khoản dịch vụ + host backup).
3. **Ưu tiên điều kiện "danh tính hợp lệ"** (tiến trình có chữ ký, tài khoản dịch vụ, host thuộc nhóm
   chức năng, lịch quét) hơn điều kiện "hành vi" — hành vi thì TP cũng làm được.
4. **Kiểm TP nghiêm trọng (.003):** liệt kê mọi alert TP có severity Nghiêm trọng/Cao (HV-01) và chạy
   tay filter qua từng cái — một cái bị lọc là mất toàn bộ điểm. HV-37 (sơ đồ mạng) giúp tránh lọc theo
   dải mạng chứa máy quan trọng.
5. **Không xoá rule, không nới rule thành vô dụng.** Filter suppress đúng nhóm FP; rule gốc giữ nguyên.

## Chẩn đoán nguyên nhân FP — `fp_cause` (T1111.002)

Tập nhãn của gold pilot: `rule_logic` · `data_quality` · `environment_change`.

| Nguyên nhân | Dấu hiệu | Hướng xử lý |
|---|---|---|
| `rule_logic` | rule thiếu điều kiện loại trừ hiển nhiên; điều kiện quá rộng; FP **suy ra được từ chính text rule** | sửa logic/thêm exclusion |
| `data_quality` | trường bị parse sai/thiếu, timestamp lệch, giá trị rỗng làm điều kiện luôn đúng; FP tập trung ở một log source có vấn đề (HV-04 sức khoẻ log source) | sửa parser/nguồn log, không sửa rule |
| `environment_change` | FP bắt đầu từ một mốc thời gian trùng với triển khai mới (agent mới, phần mềm mới, thay đổi mạng) ghi trong HV-11 ticket hoặc change log | cập nhật baseline/whitelist theo thay đổi |

Đọc HV-11 (ticket tối ưu cảnh báo) — thường ghi lại lịch sử thay đổi và phàn nàn của ca trực.

## Định dạng nộp

- Gold pilot T1111.002: `{"filter": {"all_of": [...], "any_of": [...]}, "fp_cause": "rule_logic"}`
  (filter DSL — `engines.md` §3).
- Fixture DEV tự động: `{"rule": {"engine": "regex", "pattern": "...", "ignore_case": true}}` với
  `mode: filter` — regex **khớp các dòng FP cần loại**.
- Luôn theo `manifest.output_schema`.

## Bẫy hay gặp

- Lọc theo triệu chứng chung với TP ⇒ ΔTP_mất% cao ⇒ điểm âm bị cắt về 0.
- Lọc theo IP/dải mạng rộng (đổi được, và nuốt máy quan trọng).
- Đổ lỗi `rule_logic` khi FP thật ra do một log source hỏng hoặc một đợt triển khai phần mềm.
- Quên kiểm thủ công từng TP Nghiêm trọng/Cao.
