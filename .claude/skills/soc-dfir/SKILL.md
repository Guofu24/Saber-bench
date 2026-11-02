---
name: soc-dfir
description: Điều tra chứng cứ số theo case, bảo toàn artifact và dựng timeline có dẫn chứng. Dùng cho phân tích log, disk/memory/registry được cấp; bàn giao kết quả và giới hạn cho IR, không tự cô lập hay diệt trừ.
---

# Điều tra số — DFIR

Trong world, theo [hợp đồng lab](../soc-orchestrator/reference/continuous-world.md).
Nhận case/phạm vi, cutoff, câu hỏi điều tra và artifact; thiếu nguồn thì ghi thiếu.

1. Nhận việc bằng `accept_task` khi được giao; kiểm case/revision và evidence đã có. Tìm lịch sử bằng
   `query_events`, lấy lại ID bằng `get_evidence`, gắn thêm bằng `append_evidence` trước khi kết luận.
2. Thu snapshot qua `capture_artifact` nếu có; giữ hash, nguồn, thời điểm và người thu. Phân tích trên bản sao.
   Artifact application lab không phải disk image/RAM dump. Công cụ không có thì không tuyên bố đã thu.
3. Dựng timeline theo event ID và thời gian nguồn; liên kết host/account/process đúng định danh, xét thiếu log,
   lệch giờ và giả thuyết hợp lệ. `investigate` chỉ sắp dữ liệu case, chưa thay phân tích nguyên nhân.
4. Ghi finding có dẫn chứng, phân biệt đã xác nhận/giả thuyết/chưa biết. Bàn giao IR phạm vi, điều còn thiếu,
   tác động có căn cứ và chứng cứ cần giữ trước phản ứng. Không biến đề xuất thành hành động đã thực thi.
5. Hoàn tất nhiệm vụ bằng kết quả + evidence, hoặc báo blocked với dữ liệu cần bổ sung. Không đóng sự cố thay lead.

Case artifact hệ điều hành: [bảo toàn/pháp y](../soc-ir/reference/evidence-forensics.md),
[timeline và Patient Zero](../soc-ir/reference/reconstruction.md).
Ghi hồ sơ theo [case record](../soc-orchestrator/reference/case-record.md).
