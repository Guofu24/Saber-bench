---
name: soc-platform
description: "Kiểm sức khoẻ telemetry và công cụ SOC trong phạm vi được cấp: log gap, retention, parser, clock, hàng đợi và lỗi truy vấn. Phân biệt thiếu quan sát với không có tấn công; bàn giao sửa hệ thống có kiểm chứng."
---

# Vận hành nền tảng SOC

Trong world, theo [hợp đồng lab](../soc-orchestrator/reference/continuous-world.md).

1. Dùng `telemetry_health` khi có để kiểm dữ liệu đang giữ, khoảng tick, lỗi và khả năng adapter.
   Số event ít không tự là mất log; đối chiếu lịch hoạt động/baseline đã cấp. Không có baseline thì ghi chưa đủ.
2. Kiểm phạm vi query, cutoff, pagination và retention trước khi báo hunt sạch. Archive sealed không phải nguồn
   mà agent được phép mở; bàn giao yêu cầu khôi phục dữ liệu cho operator qua kênh hiện có.
3. Khi có parser thực, giữ raw record và lỗi parse, xác minh field/type/timezone. Khi chỉ có event ứng dụng,
   không tuyên bố đã kiểm Sysmon, SIEM collector, NTP hay EDR agent.
4. Ghi tác động của log gap lên các case/rule/hypothesis. Đề xuất sửa kèm tiêu chí kiểm lại và rollback;
   không tự đổi cấu hình host hay nguồn production.
5. Bàn giao CNT lỗi field/parser; lead nhận phạm vi mù và mức khẩn theo SOP. Phục hồi nguồn phải có dữ liệu mới
   đối chiếu và đánh dấu khoảng lịch sử không khôi phục được, không xoá dấu vết gián đoạn.

Hồ sơ: [case record](../soc-orchestrator/reference/case-record.md).
