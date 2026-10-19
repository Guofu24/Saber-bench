# Bản đồ triển khai SABER cho Claude Code (Tiếng Việt)

## Tại sao không yêu cầu Claude Code code toàn bộ một lần?

Hệ thống này có ít nhất ba miền có mức độ tin cậy khác nhau: (1) hạ tầng range; (2) Blue Agent + tool gateway; (3) evaluator giữ nhãn ẩn. Nếu code đồng thời dễ tạo lỗ hổng rò nhãn, log tương lai và điểm benchmark giả. Vì vậy chia thành 38 task dạng một task/PR, có kiểm thử và review riêng.

## Thứ tự thực thi

| Giai đoạn | Task | Kết quả cần chứng minh |
|---|---|---|
| M0 — Foundation | T001–T005 | Python monorepo, CI, DTOs, DB, API, RBAC/audit |
| M1 — Offline benchmark | T006–T014 | Fixture phát log, query có chặn log tương lai, grader tách nhãn, report tái lập |
| M2 — Cyber range thật | T015–T024 | Proxmox IaC, Ansible, Wazuh, workload bình thường, emulation có phê duyệt, snapshot và success verifier |
| M3 — Agents | T025–T032 | Tool gateway, provider LLM, 4 agents, orchestration và baseline rules/single-agent |
| M4 — Nghiên cứu | T033–T038 | Hidden split theo family, ma trận thí nghiệm, detection/response tracks, dashboard, hardening và release |

## Gate đặc biệt quan trọng

- **Sau T009:** agent không thể query future events hoặc event của episode khác.
- **Sau T013:** evaluator xác định TP/FP/TN/FN và INVALID bằng code, không dùng LLM làm trọng tài chính.
- **Sau T024:** kịch bản tấn công được xác minh bằng hiệu ứng thực tế; thất bại thì INVALID, không được tính thành false negative.
- **Sau T030:** IR mặc định dry-run, thay đổi host chỉ qua action được cấp quyền và có rollback.
- **Sau T035:** track phát hiện không gây side effect; track response đo cả tác động lên workload bình thường.
- **Sau T038:** kết quả dev fixture không được quảng bá là benchmark SOC thực nghiệm.

## Workflow Claude Code

1. Tạo Git repo, đưa bộ kit này vào và chạy `claude --permission-mode plan`.
2. Prompt ở `prompts/START_CLAUDE_CODE.md` để Claude chỉ lên kế hoạch T001.
3. Duyệt kế hoạch, sau đó cho thực thi T001 và yêu cầu chạy lệnh kiểm thử thật.
4. Dùng `tasks/REPORT_TEMPLATE.md` làm báo cáo mỗi task.
5. Review độc lập qua `/gate-review T001` hoặc subagent `security-reviewer`/`benchmark-reviewer` khi phù hợp.
6. Commit/PR, sau đó bắt đầu session mới với task tiếp theo.

## Điểm kỹ thuật cần giữ

- Wazuh Manager API không đồng nghĩa raw event search: đọc từ Wazuh Indexer/OpenSearch qua adapter riêng.
- Sigma không tự chạy được trên mọi SIEM: phải test pySigma backend + field mapping phiên bản được ghim.
- P0/P1 sử dụng local `FakeEventStore` nhưng các báo cáo luôn gắn `DEV_SIMULATION_ONLY`.
- Tấn công và IR chỉ chạy trong lab cô lập có phê duyệt cụ thể, không có agent tấn công tùy ý.
- Đơn vị thống kê nên là scenario family/episode thay vì tính các log có tương quan như các quan sát độc lập.

## Thứ nên cắt nếu tài nguyên hạn chế

MVP chưa cần Windows AD, network sensor, full SOAR playbook, model fine-tuning, self-adaptive Red LLM hay dashboard realtime phức tạp. Ưu tiên dựng được **1 vertical slice có log thật, ground truth độc lập, kết quả có thể kiểm chứng và so sánh baseline công bằng**.
