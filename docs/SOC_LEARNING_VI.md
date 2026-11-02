# Học từ lỗi trong SOC range

Controller lưu episode riêng cho từng agent, gồm action, kết quả và evidence ID.
Khi bật Gemini, learner dùng đúng pool của đội và **cùng cumulative call budget** với
planner. Scripted mode vẫn ghi episode nhưng không tự tạo lời khuyên giả từ model.

Luồng: episode → reflection → đề xuất có dẫn chứng → replay base/candidate →
phiên bản bất biến → kích hoạt ở ranh giới an toàn. Không có suite do operator cài
thì proposal ở `AWAITING_SUITE`. Agent không được sửa suite hoặc tự phê duyệt.
Candidate phải vượt toàn bộ repair/regression và cải thiện lỗi so với base, với
2–3 lần lặp mỗi case. Đây là kiểm tra quyết định kế tiếp, không chứng nhận toàn bộ
khả năng điều tra hay đảm bảo bài học sẽ đúng ở mọi tình huống.

Case mở, worker/guest/analysis/SOAR job đang dở giữ nguyên phiên bản skill hiện tại.
Restart cũng giữ pin. Bài học chỉ thêm hướng dẫn; không mở rộng tool/quyền thực thi.
Office hiển thị số episode, proposal và publication; nội dung notebook vẫn riêng.

## Lệnh trong bundle trên máy đích

Đứng tại root bundle, dừng controller trước khi cài suite/rollback/đọc notebook:

```powershell
saber lab stop --bundle .
docker compose -f compose.yaml run --rm --no-deps controller saber lab learning list --out /data
docker compose -f compose.yaml run --rm --no-deps controller saber lab learning install-suite --out /data --file /config/learning/range-client.json
docker compose -f compose.yaml run --rm --no-deps controller saber lab learning versions --out /data --skill client-user
docker compose -f compose.yaml run --rm --no-deps controller saber lab learning inspect --out /data --proposal <PROPOSAL_ID>
docker compose -f compose.yaml run --rm --no-deps controller saber lab learning rollback --out /data --skill client-user --version <VERSION_ID>
saber lab resume --bundle .
```

`learning/range-client.json` là mẫu phát triển, không tự cài. Với suite riêng,
mount file operator đã review read-only vào container và đổi `--file`; không sửa
file đã được manifest bảo vệ. Một suite 3 case × 2 lần × base/candidate tốn tối đa
12 lượt model, chưa tính reflection/retry của provider. Kết quả không cải thiện
thì không publish. Các lệnh dùng `--out` là đường dẫn volume **bên trong container**.

Khi đọc snapshot đang chạy:

```powershell
docker compose -f compose.yaml exec controller saber lab learning status --out /data
```

Restore đầy đủ volume controller giữ episode, version, suite và pin; Git revert
chỉ đổi mã nguồn. Test local đã chạy capture → reflection → replay → publish →
case pin → activation → rollback bằng provider fixture; không gọi Gemini trong
đợt hoàn thiện này. Chất lượng bài học Gemini cần đánh giá trên run có API thật.
