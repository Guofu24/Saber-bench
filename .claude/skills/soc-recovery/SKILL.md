---
name: soc-recovery
description: "Xác minh phục hồi sau phản ứng: tình trạng dịch vụ, dữ liệu và quyền truy cập hợp lệ, công việc client tiếp tục được, đường tác động còn bị chặn. Không đồng nhất HTTP 200 hay restore thành công với khôi phục hoàn chỉnh."
---

# Kiểm chứng phục hồi

Trong world, theo [hợp đồng lab](../soc-orchestrator/reference/continuous-world.md).
Nhận case, hành động IR đã thực hiện và tiêu chí chấp nhận; nhiệm vụ là kiểm, không tự sửa hệ thống.

Dependency, backup/restore provenance, acceptance, cutover/rollback và observation window:
[recovery-acceptance](reference/recovery-acceptance.md). Live đọc bằng `consult_skill` trước việc chuyên sâu.

1. Lấy trạng thái và bằng chứng sau phản ứng bằng `verify_recovery` khi có; xác nhận dịch vụ hoạt động, quyền
   người dùng hợp lệ không bị chặn và biện pháp giảm thiểu còn hiệu lực. Không dùng báo cáo evaluator hay plan red.
2. Kiểm event công việc từng client bị ảnh hưởng sau mốc phản ứng: read/write/call_app phù hợp mục tiêu;
   login chỉ xác nhận phiên, chưa chứng minh công việc tiếp tục. Không có hoạt động
   mới thì ghi chưa xác minh người dùng phục hồi, không tự hành động dưới danh tính họ.
3. Phân biệt tính sẵn sàng, toàn vẹn dữ liệu và truy cập hợp lệ. HTTP 200 chưa chứng minh dữ liệu khôi phục đúng;
   cần baseline/hash/backup có thật. Lab không có backup engine thì đánh dấu phần đó chưa kiểm.
4. Nếu phát hiện chặn nhầm hoặc biện pháp đã hết hạn, mở lại/bàn giao case cho lead/IR cùng evidence; không tự
   release/restore khi vai chỉ có quyền kiểm chứng.
5. Ghi kết quả từng tiêu chí, bằng chứng, thời điểm, thiếu sót và residual risk. Lead quyết định đóng case;
   kết quả checked tại một tick không bảo đảm hệ thống an toàn mãi mãi.

Hồ sơ: [case record](../soc-orchestrator/reference/case-record.md).
