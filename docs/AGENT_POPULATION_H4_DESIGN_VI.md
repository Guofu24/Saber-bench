# SABER — Thiết kế mở rộng H4+: tự chủ (LLM) · VM/đa máy · reverse engineering

Written for: operator SABER + một reviewer độc lập + session Claude Code kế tiếp sẽ cân nhắc
greenlight. Đây là **bản thiết kế để bàn** (`DESIGN_ONLY`), KHÔNG mô tả code đã tồn tại. Không dòng
nào dưới đây được triển khai trong `src/` tại thời điểm viết. Mọi quyết định "làm / chưa làm" thuộc
về operator.

Nối tiếp: [`docs/AGENT_POPULATION_DESIGN_VI.md`](AGENT_POPULATION_DESIGN_VI.md) (H0–H4 khung gốc) và
[`docs/PHASE_H_REPORT.md`](PHASE_H_REPORT.md) (H1–H3 đã xong). Tài liệu này lấp **3 trụ cột còn
thiếu** để tiến tới "hệ thống hoàn chỉnh" mà operator mô tả: client-VM thật, red/blue tự chủ, và
nhánh reverse engineering (Ghidra/IDA).

Trạng thái: `DESIGN_ONLY` · cần operator chốt scope từng trụ cột trước khi viết code.

---

## 0. Bối cảnh — ta đang ở đâu so với mục tiêu

Mục tiêu operator: *"client đóng vai máy thật (nhiều VM) · red team tấn công · blue phòng thủ + trace
qua Ghidra · reverse qua IDA — cả một hệ thống hoàn chỉnh."*

H1–H3 đã dựng **khung chấm điểm + 2/nhiều họ tấn công**, nhưng **tất cả đều scripted, không LLM,
không VM, không reverse**. Khoảng cách thực tế:

| Trụ cột mục tiêu | Hiện trạng (H1–H3) | Tài liệu này |
|---|---|---|
| Agent tự chủ (red/blue nghĩ được) | scripted, 0 LLM | **Trụ cột 1** |
| Client = nhiều máy/VM thật | 1 service loopback, generator nhiễu | **Trụ cột 2** |
| Reverse engineering (Ghidra/IDA) | **0 dòng, chưa cả trong backlog** | **Trụ cột 3** |

Ba trụ cột này **độc lập nhau** — làm được riêng, dừng được riêng, ưu tiên được riêng.

---

## 1. Ràng buộc kế thừa (không thương lượng)

Mọi thứ dưới đây phải thỏa **5 luật bất biến** đã nêu ở `AGENT_POPULATION_DESIGN_VI.md §2`, nhắc gọn:

1. **Nhãn độc lập với agent** — truth suy từ hiệu ứng server/host thật, không từ lời agent.
2. **Attacker chỉ chọn từ allowlist** — mỗi họ có executor inert + verifier trạng thái độc lập.
3. **Isolation tuyệt đối** — `--network none`/`internal: true`, snapshot+rollback, không `sudo`,
   **không tự `docker pull`/`run`** (operator bấm tay).
4. **Fail closed + nhãn tier thấp** — thiếu lab/quyền ⇒ `BLOCKED_INTEGRATION`; kết quả lab tự động là
   `AUTOMATED_LAB_GROUND_TRUTH` < gold chuyên gia.
5. **Không rò nhãn** — blue không thấy `gold_truth`, không đọc tương lai/episode khác; prompt sinh của
   attacker/driver không được chảy vào kênh blue đọc.

Thêm luật **billing** (`CLAUDE.md`): chỉ dùng **subscription**, không bật API trả phí. ⇒ mọi thứ
dùng LLM phải có **trần ngân sách** và **cache episode** để không đốt quota.

---

## 2. Trụ cột 1 — Tự chủ: LLM-hóa driver (client + attacker)

### 2.1 Mục tiêu
Nâng "attacker/client = hàm scripted" thành **agent chọn hành động** (nghĩ được trình tự, biến thể),
để episode đa dạng hơn 4 họ cứng → đủ khó để trả lời câu hỏi gốc *"phối hợp nhiều blue-agent có hơn
1 agent / rule không"* (blocker G-1).

### 2.2 Cơ chế — generator, KHÔNG phải thí sinh
- Attacker-LLM nhận **một mục tiêu trừu tượng** ("đạt truy cập chưa phép vào webroot") + **menu
  allowlist** (`AttackAction[]` từ `attack_registry`). Nó phát ra **chuỗi `action_id + params hợp
  lệ`**. Control plane thực thi phần **inert** tương ứng. LLM **không** chạy shell tùy ý, **không**
  bịa hiệu ứng ngoài allowlist.
- Truth vẫn do `effect_verifier` đọc trạng thái thật ⇒ LLM "khai" gì cũng không đổi nhãn (luật #1).

### 2.3 Tái lập — mấu chốt (LLM là phi tất định)
Giải đúng như fuzzer:
1. Chạy attacker-LLM **một lần** → thu **chuỗi action đã phát** + evidence.
2. `run_episode` **record + seal** ngay (đã có hạ tầng này cho scripted).
3. Từ đó episode là **artifact cố định, replay được không cần LLM**. Blue chấm trên episode đã niêm
   phong. ⇒ **sinh tốn quota một lần, chấm lại miễn phí vô hạn.**
- Lưu episode đã seal vào `range_evidence/episodes/<family>/<hash>.json`; coi như test-case bất biến.

### 2.4 Cũng áp cho blue (tùy chọn)
Blue đã có `single/specialist/multi_agent` ở `soc eval`. Trụ cột này chỉ cung cấp **tập episode khó
hơn** để so sánh có ý nghĩa — không đổi contract chấm.

### 2.5 An toàn riêng của LLM-driver
- Prompt attacker **không** chứa nhãn; output bị **validate cứng** (chỉ nhận `action_id` trong
  allowlist + schema params), cái gì ngoài schema → bỏ, ghi `tool_failure`.
- Trần: `max_actions/episode`, `max_episodes/run`, timeout mỗi call (tái dùng `claude_cli` đã có:
  cwd rỗng, scrub API key, `--max-turns 1`, kill process-tree).
- Fail closed: không có subscription CLI ⇒ `BLOCKED_INTEGRATION`, không rơi về scripted âm thầm.

### 2.6 Công sức / phụ thuộc
**Trung bình. Không cần Docker.** Chỉ cần subscription. Rủi ro chính = tốn quota (đã chặn bằng
cache+trần) và chất lượng output LLM (đã chặn bằng validate allowlist).

---

## 3. Trụ cột 2 — VM / đa máy (client thật, process, lateral)

### 3.1 Mục tiêu
Từ "1 service loopback" → **nhiều máy trong một lab mạng cô lập**: nhiều client riêng IP, một host
đích, và (quan trọng) các họ tấn công **cần máy thật**: `process` (tiến trình bất thường) và
`lateral` (di chuyển ngang sang host B).

### 3.2 Hai mức, chọn theo tài nguyên
| Mức | Nền | Cho gì | Chi phí |
|---|---|---|---|
| **2a — container** | Docker Compose, mạng `internal: true` | nhiều "máy" nhẹ: 3–5 client container + 1 victim + 1 host-B; đủ cho `process` & `lateral` mô phỏng | RAM vừa; **cần Docker + WSL2** |
| **2b — VM thật** | hypervisor (Proxmox/KVM) + snapshot | OS thật, telemetry host/network thật, forensic artifact thật | cao; **cần lab được cấp phép** (mode `vm` hiện `BLOCKED_INTEGRATION`) |

Khuyến nghị: **làm 2a trước** (khớp adapter container đã có khung), 2b chỉ khi có lab thật.

### 3.3 Họ hành động mới (đã phác ở design gốc §4, nay chi tiết verifier)
| Họ | Executor inert | NHÃN (verifier độc lập) | Hard negative |
|---|---|---|---|
| `process` | spawn tiến trình **lab-only** từ allowlist trong victim container | PID xuất hiện + command/parent khớp mẫu đã định (đọc `/proc` hoặc process table container) | tác vụ admin hợp lệ cùng mẫu lệnh |
| `lateral` | mở kết nối từ victim → **host-B trong cùng lab** | log kết nối nội bộ **phía host-B** (server-side) | kết nối dịch vụ nội bộ hợp lệ (vd health-check) |
| multi-client noise | N client container, IP riêng | (không sinh nhãn — chỉ môi trường) | chính nó là hard-negative cho entity-disambiguation |

Lợi ích phụ: multi-client **vá điểm yếu hunting** hiện tại (loopback chỉ 1 entity ⇒ metric entity vô
nghĩa). Có nhiều IP/entity thì timeline/affected-entity mới có tín hiệu thật.

### 3.4 Isolation (bắt buộc)
- Mạng Docker `internal: true` (không gateway ra ngoài) hoặc `--network none` cho container không cần
  nói chuyện; lab bridge + CIDR như `infra/lab_plan.py` đã validate.
- Snapshot/teardown sạch mỗi episode; tài sản lab-only TTL.
- `docker compose up` do **operator** bấm; agent chỉ `BLOCKED_INTEGRATION` tới khi lab sống.

### 3.5 Công sức / phụ thuộc
**Cao.** 2a cần Docker/WSL2 (hiện **tắt** trên máy này — blocker CR-1); 2b cần hypervisor được cấp
phép. Đây là phần nặng nhất và phụ thuộc hạ tầng nhất.

---

## 4. Trụ cột 3 — Reverse engineering (Ghidra headless; IDA tùy chọn)

### 4.1 Mục tiêu
Một **họ subtask mới**: blue/reverse-agent phân tích **một binary** bằng công cụ RE thật, trả lời các
câu hỏi về nó; chấm so với **sự thật ta biết vì chính ta biên dịch ra binary đó**.

### 4.2 Vì sao đây là chỗ nhãn-độc-lập SẠCH nhất
Ta **tự build binary lành tính** với các thuộc tính cấy sẵn → **build manifest = ground truth** (ta
tạo ra nó, không agent nào định nghĩa). Đây là nguồn nhãn độc lập lý tưởng, không cần verifier runtime
phức tạp.

| Thành phần | Nội dung |
|---|---|
| Mẫu | binary **lành tính tự compile** (C nhỏ), vd nhúng 1 "key" giả, 1 thuật toán nhận dạng được (xor/crc), 1 chuỗi config, vài hàm đặt tên trước | 
| Ground truth | build manifest: danh sách hàm cấy, chuỗi cấy, thuật toán, API import kỳ vọng — sinh lúc compile |
| Công cụ | **Ghidra headless** (`analyzeHeadless -import <bin> -readOnly -postScript export.py`) → xuất hàm decompiled / strings / symbols |
| Câu hỏi chấm | "liệt kê API import gợi ý hành vi X" · "tìm hằng/key hardcode" · "nhận dạng thuật toán" — chấm bằng set-delta/enum/string đã có |
| Hard negative | binary lành tính nhìn-giống (hàm thư viện chuẩn, chuỗi mồi) để test precision |

Agent "khai" gì cũng chấm vs manifest ⇒ luật #1 thỏa, **mà không cần runtime verifier** như process/
lateral. Đây là lý do RE **dễ giữ hợp lệ hơn** phần VM.

### 4.3 Công cụ: Ghidra là tham chiếu, IDA tùy chọn
- **Ghidra**: image `blacktop/ghidra` (Apache-2.0, free), chạy **standalone** (project tạm local,
  `-readOnly`), **KHÔNG** dùng ví dụ client/server của image. Ta tự ép rào:
  `--network none --read-only --tmpfs ... --cap-drop ALL --memory=4g`, non-root, mẫu mount `:ro`,
  **pin `@sha256:` digest** (image từ hub = dữ liệu không tin cậy).
- **IDA**: adapter thay thế **tùy chọn** — IDAPython headless. Vướng **license thương mại theo ghế**
  ⇒ **mặc định `BLOCKED_INTEGRATION`**; chỉ bật nếu operator có license hợp lệ. Ghidra là đường chính.
- **Mẫu chỉ lành tính, tự build.** Không tự kéo malware thật (luật #3 + SECURITY.md).

### 4.4 Fail closed
Không Docker/không image/không license ⇒ adapter trả `BLOCKED_INTEGRATION`, **không bịa kết quả
decompile**. Trên máy này (Docker tắt) ⇒ land blocked cho tới khi operator bật.

### 4.5 Ánh xạ catalog
Nếu catalog NICE 175 có subtask forensics/RE phù hợp → bind đúng ID (như G2 đã bind
`T1347.001`/`T0020.001`); **không** claim coverage nếu không có contract nguồn khớp. Nếu không có →
đây là artifact RE độc lập, báo cáo trung thực là *mới*, không gắn nhãn coverage nguồn.

### 4.6 Công sức / phụ thuộc
**Trung bình.** Phần build binary + manifest + scorer **viết được ngay, offline** (không cần Docker).
Chỉ bước chạy Ghidra thật cần Docker. ⇒ có thể làm **adapter fail-closed + scorer + mẫu** trước, chạy
thật sau.

---

## 5. Lộ trình sửa đổi (nối sau H3)

Mỗi mốc kiểm chứng được, dừng được, là 1 PR có test (positive · hard-negative · invalid/missing ·
cross-episode · leakage · determinism bản đã record).

| Mốc | Nội dung | Phụ thuộc | Quota LLM | Làm được ngay? |
|---|---|---|---|---|
| **H4** | Scale 4 họ hiện có × nhiều seed; tách reliability/capability (G-1) | không | không | ✅ ngay |
| **H5 (Trụ cột 1)** | LLM sequencer cho attacker + record/seal episode; cache | subscription | có (có trần) | ✅ ngay (không cần Docker) |
| **H6 (Trụ cột 3)** | RE: build binary + manifest + scorer + adapter Ghidra **fail-closed**; chạy thật khi Docker bật | scorer: không · chạy thật: Docker | không | ⚠️ một phần (scorer offline ngay; Ghidra chờ Docker) |
| **H7 (Trụ cột 2)** | VM/đa máy: Compose 2a (multi-client + `process` + `lateral`); 2b VM thật sau | **Docker/WSL2** (CR-1) / hypervisor | không | ❌ chờ operator bật Docker |

Gợi ý thứ tự: **H4 → H5 → H6 → H7**. Lý do: H4/H5/H6(scorer) **không chờ hạ tầng**, làm được ngay
trên máy này; H7 (và phần chạy-thật của H6) phụ thuộc Docker/VM nên để sau cùng.

---

## 6. Tác động tier — vẫn KHÔNG

Cả 3 trụ cột đều **không** tự nâng bài nào lên `READY_BENCHMARK`:
- Nhãn lab tự động = `AUTOMATED_LAB_GROUND_TRUTH` < gold chuyên gia ký (ED-1 còn mở).
- `READY_BENCHMARK` vẫn cần: lab được cấp phép + chuyên gia độc lập ký + holdout mù.
- Giá trị thực: biến benchmark thành **đủ khó, đa dạng, nhiều bề mặt** (web/host/mạng/binary) để câu
  hỏi nghiên cứu *đo được* — không phải tuyên bố đã đo xong.

Bảng tier mục tiêu sau H7 **giữ nguyên**: 175 VERIFIED_OFFLINE · 65 BLOCKED_INTEGRATION · **0
READY_BENCHMARK**.

---

## 7. Rủi ro riêng của 3 trụ cột

| Rủi ro | Trụ cột | Cách chặn |
|---|---|---|
| LLM-driver đốt quota | 1 | record/seal + cache episode; trần action/episode; chấm lại không gọi LLM |
| LLM phát action ngoài luồng | 1 | validate cứng vs allowlist schema; ngoài schema → bỏ + log |
| `process`/`lateral` rò ra mạng thật | 2 | `internal: true`/`network none`; lab bridge + CIDR validate; teardown |
| Phụ thuộc Docker chặn tiến độ | 2,3 | tách phần offline (scorer/manifest/fail-closed) làm trước; chạy-thật sau |
| Kéo malware thật để RE | 3 | **chỉ binary lành tính tự build**; cấm auto-pull mẫu |
| Image Ghidra không tin cậy | 3 | pin digest; `network none`+`read-only`+`cap-drop`; non-root |
| IDA license | 3 | mặc định BLOCKED; chỉ bật khi operator có license |
| Overclaim "đã có hệ thống hoàn chỉnh" | tất cả | giữ nhãn tier thấp; report trung thực phần scripted vs tự chủ |

---

## 7b. Track mới — Chuyên biệt hóa vai (role specialization + skills)

Blue **không phải một khối**: nó là cả một tổ chức SOC nhiều vai, và red team cũng là nhiều vai. Mỗi
vai = **1 skill chi tiết** (playbook: nhiệm vụ, input được/không được đọc, quy trình, output) **+ 1
hợp đồng chấm** (chấm vs sự thật độc lập, hoặc trung thực ghi "chưa chấm"). Reverse chỉ là *một* vai.

Skill là **sổ tay tác nghiệp cho agent làm việc**, viết theo đúng 4 nghiệp vụ của catalog
(`catalog/services.json` — cũng là 4 specialist B2/B3 trong `docs/BENCHMARK_PROTOCOL.md`). Nội dung nghiệp vụ
(việc gì, quy trình, tiêu chí quyết định, FP kinh điển, đầu ra, bàn giao, rào chắn) rút từ 55 NICE task của
catalog, nhưng **không** nhắc tới cách chấm điểm (mã HV, trọng số, gate, fixture): agent được dạy làm đúng
nghề, không được dạy làm bài thi. Lớp benchmark (bài nộp, chuẩn hoá, chấm) tách riêng ở
`docs/SUBMISSION_CONTRACT_VI.md` cho người viết harness.

| Skill | Đội | Phủ NICE task | Mảng việc bên trong |
|---|---|---|---|
| `soc-mon` | Vận hành giám sát 24/7 | 16 | kiểm chứng cảnh báo, 10 nhóm cảnh báo, nguyên nhân & tác động, vòng đời case, phản ứng nhanh |
| `soc-cnt` | Content Security | 5 | viết rule/chữ ký, tối ưu FP, độ phủ ATT&CK, TI → rule |
| `soc-hunt` | Threat Hunt / CA | 13 | săn tệp/webshell, phân tích xâm nhập, ATT&CK, rà cấu hình & lỗ hổng, Technical Report |
| `soc-ir` | Xử lý sự cố | 21 | triage/điều phối, forensics, bộ nhớ, PCAP, **malware/reverse**, quy kết, diệt trừ, báo cáo |
| `redteam-initial-access` | red (mô phỏng đối thủ) | — | dò quét, khai thác web/dịch vụ, phishing, tấn công đăng nhập — chỉ menu allowlist trơ |
| `redteam-post-exploitation` | red (mô phỏng đối thủ) | — | persistence, di chuyển ngang, C2, chống điều tra, exfil — phần lớn cần lab nhiều máy |
| `soc-orchestrator` | điều phối SOC (SOC lead) | — | giao việc cho 4 đội, giữ case chung, canh SLA, xử lý bất đồng bằng bằng chứng, chuyển phê duyệt; mẫu case chung `reference/case-record.md` |
| `client-user` | client (người dùng/máy bình thường) | — | hoạt động nền lành tính theo vai + danh mục hoạt động hợp lệ dễ bị nhầm là tấn công (`reference/benign-lookalikes.md`) |

Tổng 55 NICE task — mỗi task thuộc đúng một đội. Mỗi đội có mục **bàn giao** (MON ↔ IR ↔ HUNT ↔ CNT), đi qua
agent điều phối và ghi theo mẫu case chung — đây là cấu hình "4 specialist + shared case state + orchestrator" (B3)
của `docs/BENCHMARK_PROTOCOL.md`. Agent client sinh nền lành tính thay cho script `client_driver.py` khi được LLM-hoá.

**Vị trí trong lộ trình:** skill là markdown — không cần Docker, không tốn quota. Ở H5 agent LLM của từng đội
nạp skill tương ứng; harness chuyển sản phẩm làm việc của agent thành bài nộp theo
`docs/SUBMISSION_CONTRACT_VI.md`. Red skills gắn vào driver allowlist ở H5/H7.

## 8. Ranh giới một dòng (không đổi)

**Blue = thí sinh được chấm. Client + Attacker = bộ sinh môi trường. Nhãn = hiệu ứng thật quan sát
phía server/host (hoặc build-manifest với binary ta tự tạo), không bao giờ là lời của agent.** Giữ
được dòng này thì mở rộng sang LLM, VM hay reverse bao nhiêu cũng vẫn là benchmark; phá nó thì không.
