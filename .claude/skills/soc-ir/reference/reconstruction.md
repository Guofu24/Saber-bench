# IR · Dựng lại sự cố: timeline, Patient Zero, bản đồ lây nhiễm

## Phân tích dòng thời gian

Dựng dòng thời gian sự cố **từ lúc bắt đầu xâm nhập tới lúc bị phát hiện**, đối chiếu log đa nguồn: SIEM, EDR,
Firewall, hệ thống xác thực, Cloud. Đầu ra: timeline chi tiết trình tự hành vi của attacker.

**Chuẩn hoá thời gian — làm trước mọi thứ**
1. Mỗi sự kiện có **giờ địa phương + offset UTC** (vd `+07:00`, `+00:00`, `-05:00`). Giờ UTC = giờ địa phương **trừ**
   offset: `10:00+07:00` = `03:00Z`.
2. Nguồn không ghi offset: lấy múi giờ **cấu hình của nguồn log** (danh mục log source), không đoán theo vị trí máy.
3. Tính đến lệch đồng hồ giữa các nguồn nếu có thông tin clock skew.
4. **Không bao giờ sắp theo chuỗi giờ địa phương**: hai sự kiện ở hai múi giờ có thể trông theo một thứ tự nhưng thứ
   tự UTC thật lại ngược.

**Dựng timeline**
- Sắp **mọi** sự kiện theo UTC; mỗi sự kiện kèm giờ UTC chuẩn (`YYYY-MM-DDTHH:MM:SSZ`), thẳng hàng với thứ tự.
- **Sáu mốc bắt buộc** của một timeline sự cố: **initial access · leo thang đặc quyền · lateral movement · persistence
  · exfiltration · phát hiện**. Mỗi mốc là sự kiện **sớm nhất có bằng chứng** cho giai đoạn đó; sai lệch quá ±5 phút
  coi như sai mốc. "Phát hiện" là lúc hệ thống/analyst phát hiện (cảnh báo đầu tiên), không phải lúc attacker hành động.

```json
{"event_order": ["evt-07", "evt-02", "evt-11"],
 "utc_times": ["2026-10-17T03:00:00Z", "2026-10-17T03:04:10Z", "2026-10-17T03:20:00Z"],
 "milestones": [{"stage": "initial_access", "event": "evt-07", "t": "2026-10-17T03:00:00Z"},
                {"stage": "detection", "event": "evt-31", "t": "2026-10-17T06:45:00Z"}]}
```

## Tái dựng cuộc tấn công

Xác định **Patient Zero** và điểm xâm nhập đầu tiên, vẽ **bản đồ lây nhiễm** (lộ trình lateral movement), liệt kê máy
và tài khoản bị chiếm quyền. Đầu ra: Attack Path & Lateral Movement Map, danh sách hệ thống và tài khoản bị ảnh hưởng.

**Xác định Patient Zero**
1. Patient Zero = máy **đầu tiên bị attacker kiểm soát** — nơi có **điểm vào** (khai thác dịch vụ phơi ra ngoài, thực
   thi từ email/tài liệu, đăng nhập đầu tiên bằng thông tin bị lộ) và từ đó các cạnh lây nhiễm toả ra.
2. Đi ngược đồ thị di chuyển ngang: máy nào là **nguồn** của các cạnh độc mà **không là đích** của cạnh độc nào trước nó?
3. **Timestamp sớm nhất không phải tiêu chí.** Một máy có thể có dấu vết sớm hơn nhưng do **quét lỗ hổng hợp lệ**
   (đúng lịch quét, scanner trong whitelist, có ticket lỗ hổng) — loại nó. Tiêu chí là **hoạt động độc đầu tiên có chuỗi
   nhân quả nối tới phần còn lại**.

**Bản đồ lây nhiễm**
- Cạnh = attacker đi từ `src` sang `dst` bằng `account`, kèm `logon_type` (3 network, 10 RDP…).
- Chỉ cạnh **độc**: tài khoản bị chiếm, nguồn không phải jump host/PAM, có thực thi từ xa đi kèm. Không đưa phiên quản
  trị hợp lệ.
- Hướng cạnh theo chiều di chuyển của attacker; host dùng tên ngắn; account bỏ domain.

```json
{"patient_zero": "web-01",
 "infection_edges": [{"src": "web-01", "dst": "srv-db-01", "account": "svc_web", "logon_type": "3"},
                     {"src": "srv-db-01", "dst": "dc-01", "account": "admin.backup", "logon_type": "10"}],
 "timeline": ["…"], "evidence": ["…"]}
```

## Sai lầm thường gặp

- Sắp theo giờ địa phương; quên rằng `+07:00` phải trừ 7 giờ để ra UTC.
- Danh sách giờ UTC không thẳng hàng với thứ tự sự kiện.
- Chọn Patient Zero theo timestamp sớm nhất (dính máy bị quét lỗ hổng hợp lệ).
- Đảo hướng cạnh; thêm cạnh quản trị hợp lệ; thiếu logon type.

Nguồn nghiệp vụ: NICE T0173, T1391 (catalog SABER).
