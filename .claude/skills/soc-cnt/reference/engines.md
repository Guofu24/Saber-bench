# CNT · Engine thực thi rule — viết rule chạy được và không bị phạt

Mọi rule do agent viết đều là **mã không tin cậy**: chạy trong sandbox (`src/saber/grading/execsandbox.py`),
có timeout, giới hạn tài nguyên, giới hạn độ dài pattern. **Không parse được hoặc timeout ⇒ 0** (ở
T0020.003 đó còn là gate `parse_ok` nhân 0 toàn bài). Không bao giờ chạy rule trên hệ thống thật.

## Engine nào chạy rule của bạn?

| Mục chấm trong đề | Fixture DEV tự động (163 subtask) | Exemplar / gold pilot (dữ liệu nghiệp vụ) | Hệ thống thật |
|---|---|---|---|
| `exec/corpus` (regex/SIEM rule, hunt query) | **regex** trên `corpus.lines` | regex (T0020.001) | SIEM đích — `BLOCKED_INTEGRATION` |
| `exec/samples` (YARA) | **regex** trên corpus (cấu trúc) | **yara_subset** (gold T1406.001) | YARA thật — chưa tích hợp |
| `exec/replay` (filter FP) | **regex** chọn dòng cần lọc (`mode: filter`) | **filter DSL** (gold T1111.002) | SIEM — `BLOCKED_INTEGRATION` |
| `exec/pcap` (Suricata) | **regex** trên corpus (cấu trúc) | — | Suricata/NSM — `BLOCKED_INTEGRATION` |

⇒ Luôn đọc `manifest.output_schema` và `objective`/`mode` trong input để biết engine thực tế. Fixture
DEV có `corpus: {lines, format: "ts event tag id"}` và `mode: detect|filter`.

## 1. regex — `{"engine": "regex", "pattern": "...", "ignore_case": true}`

- Rule khớp **từng dòng** (search, không cần khớp cả dòng). Dòng khớp = "bắt được".
- `mode: detect` ⇒ khớp dòng kỹ thuật cần bắt. `mode: filter` ⇒ khớp dòng **FP cần loại** (không được
  khớp TP).
- Viết tốt:
  - Bám **đặc điểm phân biệt bền vững** của kỹ thuật (tổ hợp token, cấu trúc), không bám giá trị đổi được
    (IP, timestamp, ID ngẫu nhiên).
  - Dùng ranh giới (`\b`, dấu phân cách trường) để không khớp chuỗi con lành tính.
  - **Tránh backtracking thảm hoạ** (`(a+)+`, `(.*)*`, lồng lượng từ trên cùng một tập ký tự) — corpus
    200.000 dòng sẽ làm timeout ⇒ 0.
  - Không dùng `.*` mở đầu/kết thúc vô ích; không dùng pattern rỗng; giữ dưới giới hạn độ dài.
  - Thử pattern trên **cả** dòng dương và hard negative trước khi nộp (đọc tay corpus công khai).

## 2. yara_subset — rule dạng YARA rút gọn

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

- `name`: định danh `^[A-Za-z_][A-Za-z0-9_]*$`. Mỗi string bắt đầu bằng `$`; `kind` ∈ `text|hex|regex`.
- `condition`: `any of them` · `all of them` · `N of them` · biểu thức boolean trên `$tên`.
- Viết tốt:
  - Bám **chuỗi cấu hình/định danh họ** (marker config, mutex, đường dẫn PDB, chuỗi C2 format) — thứ
    giữ nguyên qua biến thể. **Không bám hash** (T1406.002: nửa tập dương đã đổi hash giữ hành vi ⇒
    luật theo hash rớt recall về 0.5).
  - **Near-miss:** công cụ lành tính có thể mang chuỗi cùng *hình dạng* (`cfg=SynthBackup;v=3;` vs
    `cfg=SynthBeacon;v=3;`). Phải khớp phần **phân biệt** (tên họ), không khớp khung chung (`cfg=…;v=3;`).
  - Kết hợp 2+ chuỗi độc lập bằng `and` để giảm FP; tránh `any of them` khi có chuỗi phổ biến.
  - Chấm F1 theo mẫu ⇒ một file sạch bị bắt cũng đắt như một mẫu bị sót.

## 3. filter DSL — luật lọc FP

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

- Một bản ghi **bị lọc** khi mọi điều kiện `all_of` đúng **và** (nếu có `any_of`) ít nhất một điều kiện
  `any_of` đúng. Filter rỗng không lọc gì.
- Toán tử: `eq`, `ne` (so chuỗi không phân biệt hoa thường), `in`, `not_in`, `contains`,
  `not_contains`, `gte`, `lte` (số), `regex` (search, không phân biệt hoa thường), `exists`, `missing`.
- `field` dùng đường dẫn chấm (`a.b.c`), ký tự `[A-Za-z0-9_.]`.
- Tên field nộp bài theo đúng schema của đề (gold T1111.002 dùng khoá `filter`; fixture DEV dùng
  `rule` regex ở `mode: filter`).
- Viết tốt: **lọc theo nguyên nhân FP**, không theo triệu chứng chung với TP. Ví dụ gold T1111.002: lọc
  thuần theo "đọc nhiều file" sẽ lọc luôn ransomware thật (TP) — phải thêm điều kiện về tiến trình/tài
  khoản hợp lệ.

## Kiểm tra trước khi nộp (tự rà, không chạy grader)

1. Rule parse được (regex compile, YARA đúng schema, filter đúng toán tử)?
2. Khớp mọi dòng/mẫu dương bạn xác định được từ corpus công khai?
3. Không khớp hard negative nào (SQL-word, near-miss, admin hợp lệ, file framework)?
4. Không có pattern có nguy cơ backtracking trên input lớn?
5. Ở bài lọc: không lọc mất **TP mức Nghiêm trọng/Cao** nào (gate T1111.003)?
