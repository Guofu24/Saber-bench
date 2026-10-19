# Source gaps cần xử lý trước khi code tự đoán

1. **Nhãn và bằng chứng**: HTML không đính kèm 175 data corpora/ground truth. Ai cung cấp/duyệt bộ chuẩn cho từng subtask, đặc biệt SOAR của khách hàng? Đừng sinh gold answer bằng chính LLM đang bị benchmark.
2. **Độ khó**: các mã `.001/.002/.003` biểu diễn complexity tiến triển nhưng không bảo đảm ba cấp đều file→SOC→VM. Ví dụ `T1389.001` đã là VM; `T1348` có 13 subtask.
3. **`n` khác 0**: `T1112.003=1`, `T1299.003=1`, `T1348.003=1`, `T1389.001="2 (Hằng)"`, `T1487.001=3`. Cần kiểm tra file mẫu thật; không chứng minh tests pass hay sẵn cho agent.
4. **`*tự sinh khi dựng bài*`**: nhiều output chưa có schema artifact gắn HV, phải định nghĩa output contract.
5. **SLA**: bốn dịch vụ có SLA khác nhau; không rải chung một hạn 30 phút cho mọi case. IR intake SLA và Content turnaround là metric riêng từ detection accuracy.
6. **Multi-task reuse**: NICE task cùng loại có thể xuất hiện trong nhiều dịch vụ, nhưng mỗi subtask `T####.NNN` ở đây có một primary service. Không clone same scored episode sang nhiều service để thổi sample size.
7. **T1348 10 nhóm alert bổ sung**: schema 3-way classification và TP/FP cùng tồn tại; phải quyết định quan hệ giữa 2 nhãn và lấy mẫu hard-negative đúng mỗi nhóm.
8. **VM destructive tasks**: không dùng live malware/credential theft để 'lấp' chỗ thiếu; dùng authorized inert/safe test fixtures và đánh giá state removal. Chỉ chạy dưới approval và isolation proof.
9. **Scoring formulas**: source có nhiều biểu thức `max(0,...)`, `Σwᵢ`, `Πgate` chưa nêu quy ước tập rỗng, duplicate, ties. Bắt buộc sign-off theo phiên bản.
10. **Source references**: tên sản phẩm SOC trong file mô tả năng lực nghiệp vụ, không chứng minh mọi API/hệ thống đã được cấp cho project. Ghi dependency/blocker thay vì fake integration PASS.
