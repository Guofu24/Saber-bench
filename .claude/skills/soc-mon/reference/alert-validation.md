# MON · Kiểm chứng cảnh báo

Kiểm chứng là bước đầu tiên của mọi cảnh báo và có KPI riêng: đồng hồ SLA chạy từ lúc cảnh báo sinh ra
tới lúc bạn gán nó vào case hoặc đóng FP.

## Kiểm chứng một cảnh báo

**Dữ liệu cần:** cảnh báo gốc (rule, host, user, mức, thời điểm, mô tả, tệp/tiến trình bị cảnh báo), log thô
±60 phút quanh cảnh báo, telemetry tiến trình, danh mục tài sản, whitelist, danh mục log source.

**Quy trình**
1. **Đọc điều cảnh báo khẳng định**, không đọc tên rule. Vd: "một interpreter do tài liệu Office sinh ra rồi
   kết nối ra ngoài". Tên rule có thể gắn nhầm nhóm (rule "port scan" mà nội dung là beacon).
2. **Tìm bằng chứng xác nhận hoặc bác bỏ** điều đó: sự kiện cha–con trong telemetry, kết nối ra trong
   netconn/flow, nội dung tệp (hash, chữ ký, chuỗi).
3. **Đối chiếu ngữ cảnh hợp lệ** — mỗi dấu hiệu dưới đây kéo về FP:
   - có change ticket còn hiệu lực, đúng khung giờ thay đổi đã duyệt;
   - nguồn nằm trong subnet quản trị; người thực hiện là admin có thẩm quyền;
   - tệp ký bởi nhà cung cấp tin cậy; công cụ quản trị phổ biến trong tổ chức;
   - khớp whitelist nội bộ (đúng tài khoản, đúng máy nguồn, đúng công cụ, đúng lịch).
   Một dấu hiệu đơn lẻ (vd chỉ có chữ ký) chưa đủ — cần ngữ cảnh đi cùng.
4. **Xác định rule nào thực sự khớp và trên tài sản nào** từ chính bản ghi log, không suy từ tiêu đề cảnh báo.
5. **Kết luận**, và nếu bằng chứng không đủ để xác nhận hay bác bỏ thì kết luận "chưa xác định".

**Tiêu chí kết luận**

| Kết luận | Khi nào | Nhất quán với |
|---|---|---|
| `TRUE_POSITIVE` | bằng chứng xác nhận hành vi độc hại mà cảnh báo mô tả | claim `confirmed`, claim của cảnh báo `valid` |
| `FALSE_POSITIVE` | bằng chứng bác bỏ, hoặc là hoạt động hợp lệ có ngữ cảnh chứng minh | claim `refuted`, claim `invalid` |
| `INCONCLUSIVE` | thiếu nguồn/thiếu bằng chứng để kết luận | claim `unverified`, ghi rõ cần thêm gì |

**Đầu ra — phán quyết trong case**

```json
{
  "alert_id": "ALERT-…",
  "verdict": "TP",
  "classification": "TRUE_POSITIVE",
  "claim_confirmed": "confirmed",
  "alert_claim": "valid",
  "triggering_rule": "<rule thực sự khớp, chép đúng tên trong log>",
  "affected_asset": "<host bị tác động>",
  "explain": ["PROC-…", "LOG-…"],
  "note": "winword.exe sinh interpreter với tham số mã hoá, ngay sau đó kết nối ra host hiếm"
}
```

`explain` chỉ chứa ID bản ghi có thật chứng minh cho kết luận.

## Thẩm định cảnh báo IDS

Chỉ thẩm định cảnh báo từ sensor **nằm trong phạm vi log source đã on-board** theo hợp đồng.

**Quy trình**
1. Tách đúng phiên mà cảnh báo trỏ tới (5-tuple + thời điểm) trong PCAP.
2. Dựng lại payload tầng ứng dụng (URI, body HTTP, truy vấn DNS…) và tìm **đoạn byte làm chữ ký khớp**.
3. TP khi payload thật sự mang nội dung độc hại như chữ ký mô tả; FP khi chữ ký khớp nhầm (chuỗi giống nhưng
   ngữ cảnh lành tính — nội dung tài liệu, ô tìm kiếm) hoặc phiên không chứa payload đó.
4. **Có NAT trong đường đi**: truy ngược IP nguồn **thật** qua bảng NAT, log firewall và flow — IP mà IDS
   nhìn thấy có thể là IP sau NAT.
5. **Chấm lại mức độ theo vai trò máy đích** (máy chủ core, hệ thống cấp 3, máy VIP nặng hơn máy trạm
   thường) theo ma trận của khách hàng; không chép mức gốc của IDS.

**Đầu ra**

```json
{
  "verdict": "TP",
  "payload_offset": {"start": 212, "end": 247},
  "real_src_ip": "10.20.3.15",
  "real_severity": "Cao",
  "evidence": ["…"]
}
```

`payload_offset` khoanh **đúng đoạn khớp chữ ký**, không khoanh cả gói; nói rõ gốc offset (đầu payload ứng
dụng hay đầu gói).

## Sai lầm thường gặp

- Kết TP vì tên rule nghe nguy hiểm; kết FP chỉ vì tệp có chữ ký.
- Chép tên rule từ tiêu đề cảnh báo thay vì từ dòng log thực sự khớp.
- Báo IP sau NAT là nguồn tấn công.
- Đưa vào phần giải thích một ID không tồn tại trong dữ liệu.

Nguồn nghiệp vụ: NICE T1112, T1387 (catalog SABER).
