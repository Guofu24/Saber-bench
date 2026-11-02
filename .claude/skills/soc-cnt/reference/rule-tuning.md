# CNT · Tối ưu rule nhiễu và chẩn đoán nguyên nhân FP

Quản trị cập nhật rule/chữ ký: cập nhật định kỳ tháng/quý dựa trên kết quả IR và cảnh báo Cao/Nghiêm trọng từ
TI; đóng gói theo phiên bản; quản trị vòng đời. Gói Advanced: **tối ưu ít nhất 10 rule mỗi tháng**. Rule nhiễu
(> 50 alert/8 giờ) phải xử lý trong **4 giờ** — rule nhiễu đốt thời gian ca trực và che khuất cảnh báo thật.

## Mục tiêu khi tối ưu

Giảm FP **mà không mất TP**, đặc biệt TP mức Nghiêm trọng/Cao theo yêu cầu case. Báo số đo trên corpus đã kiểm;
không coi tỷ lệ mất TP nào là mặc định chấp nhận được hoặc suy ra chất lượng production từ corpus nhỏ.

## Quy trình tối ưu một rule

1. **Gom FP theo đặc điểm chung** (thống kê alert theo rule): cùng tiến trình cha, cùng tài khoản dịch vụ, cùng
   host/nhóm host, cùng khung giờ, cùng đường dẫn/tham số. Tìm 1–3 cụm giải thích phần lớn FP.
2. **Đặt từng cụm cạnh các TP**: điều kiện lọc phải **đúng với FP và sai với mọi TP**. Nếu TP cũng có đặc điểm đó
   (vd "đọc rất nhiều tệp" — ransomware thật cũng vậy), thêm điều kiện thu hẹp (tiến trình hợp lệ + tài khoản dịch
   vụ + host backup).
3. Kết hợp danh tính, hành vi, đích và lịch có căn cứ; chữ ký/tài khoản dịch vụ cũng có thể bị lạm dụng.
   Không allowlist rộng theo tên process/nhà phát hành; kiểm cả trường hợp attacker dùng chính công cụ hợp lệ.
4. **Kiểm từng TP Nghiêm trọng/Cao** bằng tay qua bộ lọc; dùng sơ đồ mạng để tránh lọc theo dải mạng chứa máy
   quan trọng.
5. **Không xoá rule, không nới rule tới mức vô dụng.** Bộ lọc chỉ loại đúng nhóm FP; rule gốc giữ nguyên.
6. Ghi vào ticket tối ưu: cụm FP, điều kiện lọc, số FP loại được, xác nhận không mất TP nghiêm trọng.

## Chẩn đoán nguyên nhân FP

| Nguyên nhân | Dấu hiệu | Hướng xử lý |
|---|---|---|
| `rule_logic` — logic rule | rule thiếu điều kiện loại trừ hiển nhiên, điều kiện quá rộng; FP **suy ra được từ chính nội dung rule** | sửa logic / thêm exclusion |
| `data_quality` — chất lượng dữ liệu | trường bị parse sai/thiếu, timestamp lệch, giá trị rỗng làm điều kiện luôn đúng; FP dồn vào một log source có vấn đề (xem sức khoẻ log source) | sửa parser/nguồn log, **không** sửa rule |
| `environment_change` — thay đổi môi trường | FP bắt đầu đúng thời điểm triển khai mới (agent, phần mềm, thay đổi mạng) ghi trong ticket/change log | cập nhật baseline/whitelist theo thay đổi |

Đọc ticket tối ưu cảnh báo — thường ghi lịch sử thay đổi và phản ánh của ca trực.

**Đầu ra**

```json
{"filter": {"all_of": [{"field": "process.parent", "op": "eq", "value": "backup-agent.exe"},
                       {"field": "user", "op": "eq", "value": "svc_backup"}]},
 "fp_cause": "rule_logic",
 "no_critical_tp_lost": "đã kiểm 4/4 TP mức Cao — không bị lọc",
 "result": {"fp_removed": 41, "tp_lost": 0}}
```

## Sai lầm thường gặp

- Lọc theo triệu chứng chung với TP ⇒ mất TP.
- Lọc theo IP/dải mạng rộng (dễ đổi, và nuốt cả máy quan trọng).
- Đổ lỗi cho logic rule khi thật ra một nguồn log đang hỏng hoặc vừa có đợt triển khai phần mềm.
- Không kiểm thủ công từng TP Nghiêm trọng/Cao.

Nguồn nghiệp vụ: NICE T1111 (catalog SABER).
