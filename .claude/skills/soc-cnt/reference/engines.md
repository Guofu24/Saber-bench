# CNT · Viết rule chạy được: định dạng và kiểm thử

Rule do bạn viết luôn được **chạy thử trong sandbox** (có timeout, giới hạn tài nguyên, giới hạn độ dài
pattern) trên corpus trước khi phát hành. Rule **không parse được** hoặc **chạy quá thời gian** coi như hỏng.
Không bao giờ chạy rule thử nghiệm trực tiếp trên hệ thống production.

Nếu SIEM/NSM đích có cú pháp riêng (Sigma, SPL, KQL, Suricata…) và môi trường cấp engine tương ứng, viết theo
cú pháp đó. Ba định dạng dưới đây thuộc adapter kiểm thử SABER khi task cấp adapter tương ứng; không phải cú pháp
native được mọi SIEM/YARA engine hiểu. Kiểm schema/engine/version được cấp; thiếu engine thì báo chưa kiểm thử.

## 1. Rule regex trên log — `{"engine": "regex", "pattern": "...", "ignore_case": true}`

- Khớp **từng dòng** (tìm kiếm, không cần khớp cả dòng). Dòng khớp = rule bắt.
- Ở chế độ **phát hiện**: khớp dòng chứa kỹ thuật cần bắt. Ở chế độ **lọc FP**: khớp dòng FP cần loại — tuyệt
  đối không khớp TP.
- Viết tốt:
  - bám **đặc điểm phân biệt bền vững** (tổ hợp token, cấu trúc), không bám IP/timestamp/ID ngẫu nhiên;
  - dùng ranh giới (`\b`, dấu phân cách trường) để không dính chuỗi con lành tính;
  - **tránh backtracking thảm hoạ** (`(a+)+`, `(.*)*`, lượng từ lồng nhau trên cùng tập ký tự) — corpus hàng
    trăm nghìn dòng sẽ làm rule chạy quá giờ;
  - không mở đầu/kết thúc bằng `.*` vô ích; không để pattern rỗng.

## 2. YARA (rút gọn)

```json
{
  "name": "Fam_SynthBeacon",
  "strings": {
    "$cfg": {"kind": "text", "value": "cfg=SynthBeacon;", "nocase": false},
    "$hdr": {"kind": "hex", "value": "4D 5A 90 00"},
    "$re":  {"kind": "regex", "value": "id=[0-9a-f]{8}"}
  },
  "condition": "$cfg and ($hdr or $re)"
}
```

- `name`: chữ cái/số/gạch dưới, không bắt đầu bằng số. Mỗi string bắt đầu bằng `$`; `kind` ∈ `text | hex | regex`.
- `condition`: `any of them` · `all of them` · `N of them` · biểu thức boolean trên `$tên`.
- Viết tốt:
  - bám **chuỗi cấu hình/định danh của họ mã độc** (marker cấu hình, mutex, đường dẫn PDB, định dạng URL C2,
    chuỗi lỗi đặc thù) — thứ giữ nguyên qua biến thể; **không bám hash**;
  - cẩn thận **chuỗi gần giống**: công cụ lành tính có thể mang chuỗi cùng hình dạng (`cfg=SynthBackup;v=3;` so
    với `cfg=SynthBeacon;v=3;`) — khớp phần **phân biệt** (tên họ), không khớp khung chung;
  - kết hợp ≥2 chuỗi độc lập bằng `and`; tránh `any of them` khi có chuỗi phổ biến.

## 3. Bộ lọc FP (suppression filter)

```json
{
  "filter": {
    "all_of": [
      {"field": "process.parent", "op": "eq", "value": "backup-agent.exe"},
      {"field": "user", "op": "in", "value": ["svc_backup", "svc_backup2"]}
    ],
    "any_of": [
      {"field": "host", "op": "regex", "value": "^bk-srv-\\d+$"}
    ]
  }
}
```

- Một cảnh báo **bị lọc** khi mọi điều kiện `all_of` đúng **và** (nếu có `any_of`) ít nhất một điều kiện
  `any_of` đúng. Bộ lọc rỗng không lọc gì.
- Toán tử: `eq`, `ne` (so chuỗi không phân biệt hoa thường), `in`, `not_in`, `contains`, `not_contains`,
  `gte`, `lte` (số), `regex` (tìm kiếm, không phân biệt hoa thường), `exists`, `missing`. `field` là đường dẫn
  lồng nhau dạng `a.b.c`.
- Lọc theo **nguyên nhân FP**, không theo triệu chứng chung với TP (xem `rule-tuning.md`).

## Checklist trước khi phát hành một rule

1. Parse được trên engine đích?
2. Bắt đủ mọi mẫu dương bạn xác định được trong corpus?
3. Không bắt mẫu âm nào (từ khoá lành tính, chuỗi gần giống, hoạt động quản trị, tệp framework)?
4. Không có pattern nguy cơ backtracking trên dữ liệu lớn?
5. Với bộ lọc: không lọc mất TP mức Nghiêm trọng/Cao nào?
6. Đã ghi technique ATT&CK, nguồn log cần, phiên bản và ví dụ TP/FP vào ghi chú phát hành?
