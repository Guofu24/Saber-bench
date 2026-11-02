# Mẫu case chung

Mọi agent blue (MON, HUNT, IR, Content Security) và agent điều phối cùng đọc và ghi **một bản ghi case** cho mỗi sự
việc. Đây là nguồn sự thật chung: ai mở case sau cũng phải hiểu được chuyện gì đã xảy ra, ai đã làm gì, căn cứ vào
đâu, đang chờ gì — mà không phải hỏi lại.

## Vòng đời trạng thái

```
OPEN ─► TRIAGED ─► INVESTIGATING ─► CONTAINED ─► ERADICATED ─► RECOVERED ─► CLOSED
   └─────────────► CLOSED_FP  (kiểm chứng xong, là False Positive)
bất kỳ trạng thái nào ─► ESCALATED (đang chờ tier/đội cao hơn nhận) ─► quay lại trạng thái tương ứng
```

- Chỉ chủ sở hữu hiện tại chuyển trạng thái; mỗi lần chuyển ghi một mục worklog nêu lý do.
- Không đóng case khi còn thiếu mục bắt buộc của hồ sơ (xem `../../soc-ir/reference/triage-coordination.md`).

## Cấu trúc bản ghi

```json
{
  "case_id": "CASE-185045",
  "customer": "khach-a",
  "status": "INVESTIGATING",
  "owner": "IR",
  "severity": "Cao",
  "matrix_cell": "<hàng phạm vi> × <cột mức độ>",
  "incident_type": "…",
  "opened_at": "2026-10-17T04:21:00Z",
  "sla": {"respond_by": "…", "escalate_by": "…", "report_by": "…"},
  "alerts": ["ALERT-7491e7"],
  "verdict": {"classification": "TRUE_POSITIVE", "by": "MON", "evidence": ["PROC-40cacb", "LOG-51c304"]},
  "scope": {"hosts": ["ws-it-01"], "accounts": ["an.nv"],
            "level": {"ws-it-01": "bị_kiểm_soát"}},
  "timeline": [{"t": "2026-10-17T03:58:00Z", "event": "…", "evidence": ["…"]}],
  "ioc": {"ipv4": [], "domain": [], "url": [], "sha256": [], "email": [], "cve": []},
  "attck": ["T1566.001", "T1059.001"],
  "actions": [
    {"action": "memory_dump", "object": "ws-it-01", "layer": "endpoint",
     "proposed_by": "IR", "approval_id": "APPR-…", "executed_by": "…", "verified": true}
  ],
  "notifications": [{"to": ["…"], "channel": "hotline", "at": "…"}],
  "handoffs": [{"from": "MON", "to": "IR", "at": "…", "note": "…"}],
  "worklog": [
    {"at": "2026-10-17T04:23:00Z", "by": "MON", "entry": "…", "evidence": ["…"]}
  ],
  "open_questions": ["chưa có log proxy 03:00–04:00"],
  "reports": {"preliminary": null, "technical": null, "executive": null}
}
```

## Quy tắc ghi

1. **Worklog chỉ ghi thêm.** Không sửa, không xoá mục cũ; sai thì ghi mục mới đính chính.
2. **Mọi khẳng định có `evidence`** — ID bản ghi thật trong dữ liệu giám sát. Không bịa ID.
3. **Mỗi mục ghi rõ `by` và `at`** (đội và thời điểm UTC).
4. **Một chủ sở hữu** (`owner`) tại mỗi thời điểm; chuyển chủ thì thêm mục `handoffs`.
5. **Hành động phản ứng** luôn có người đề xuất, mã phê duyệt, người thực thi, kết quả kiểm chứng.
6. **Điều chưa biết ghi vào `open_questions`**, không lấp bằng suy đoán.
7. **Không ghi thông tin của khách hàng khác** vào case.

## Ghi chú bàn giao (mẫu)

```
Từ: MON  →  Tới: IR        Lúc: 2026-10-17T04:40:00Z
Đã xác nhận: TRUE_POSITIVE — winword.exe sinh PowerShell mã hoá, beacon tới 203.0.113.9 (PROC-40cacb, LOG-51c304)
Đã làm: thu RAM ws-it-01 (APPR-…, đã kiểm chứng), chưa cô lập
Lý do chuyển: chưa có hướng dẫn cho loại sự cố; kết nối C2 còn hoạt động
Đang chờ: IR khoanh phạm vi; hạn phản hồi 05:00Z
Câu hỏi mở: thiếu log proxy 03:00–04:00
```
