# SABER — Thiết kế quần thể agent client / attacker / blue (DESIGN, chưa code)

> **Tài liệu thiết kế lịch sử.** Các trạng thái và yêu cầu go-ahead bên dưới mô tả
> thời điểm viết; sau đó người dùng đã yêu cầu triển khai quần thể agent.
> Xem [bản bàn giao hiện tại](HANDOFF.md) và code để biết phần đã thực hiện,
> thay vì coi `DESIGN_ONLY` ở đây là trạng thái hiện tại của toàn dự án.

Written for: operator SABER + một reviewer độc lập + session Claude Code kế tiếp sẽ cân nhắc có
greenlight hướng này không. Đây là **bản thiết kế để bàn**, KHÔNG phải mô tả code đã tồn tại. Không
dòng nào trong đây được triển khai trong `src/` tại thời điểm viết. Mọi quyết định "được làm / chưa
được làm" vẫn thuộc về operator.

Trạng thái: `DESIGN_ONLY` · cần operator chốt scope trước khi viết code · khớp ghi chú ở
[bản bàn giao Phase G](history/HANDOFF_PHASE_G.md) §7
("self-operating red/blue agent population" — *cần go-ahead rõ ràng* tại thời điểm đó).

Liên quan: `docs/BENCHMARK_PROTOCOL.md` (luật nhãn & leakage), `docs/SECURITY.md` (isolation),
`src/saber/range/live/` (lab live hiện có), `src/saber/soc/` (4 dịch vụ blue hiện có), `CLAUDE.md`
(luật cứng).

---

## 0. Một đoạn tóm tắt

Ý tưởng của operator: ba quần thể agent cùng chạy trong một lab cô lập —

1. **Client** đóng vai người dùng bình thường (đăng nhập ứng dụng, lướt web, chơi game…) → sinh
   "nhiễu nền" lành tính.
2. **Attacker** cố gắng dò, khai thác, chiếm quyền.
3. **Blue team** quan sát log, dựng timeline, phân tích, ngăn chặn.

**Làm được**, và nó khớp đúng xương kiến trúc đang có. Nhưng chỉ có giá trị benchmark nếu giữ **một
ranh giới sống còn**: blue team là *thí sinh được chấm*; client + attacker là *bộ sinh môi trường*;
và **nhãn đúng không bao giờ lấy từ lời của agent** mà suy từ **hiệu ứng thật quan sát phía server/host**.
Phá ranh giới này → benchmark tự chấm theo trí nhớ của chính agent → đúng cái `CLAUDE.md` cấm, và
đó là lý do hiện có 0/175 bài `READY_BENCHMARK`.

Bản thiết kế này mô tả cách giữ ranh giới đó, map vào module đang có, chỉ ra cạm bẫy, và chia việc
thành các mốc nhỏ kiểm chứng được.

---

## 1. Ta đã có sẵn những gì (điểm tựa, không phải làm lại từ đầu)

Phase F–G đã dựng đúng khuôn mẫu cần mở rộng:

| Thành phần đang có | File | Vai trong thiết kế mới |
|---|---|---|
| Scenario = plan `{target, intent}`, intent ∈ {benign, probe} | `range/live/scenarios.py` | Tiền thân của **attacker + client** ở dạng scripted |
| Control plane gửi plan → service loopback thật, thu log thật | `range/live/controlplane.py` | Giữ nguyên, là nơi "chạy episode" |
| **Truth suy từ log phía server** (`_derive_truth`), độc lập nhãn sinh | `controlplane.py:186` | **Trụ cột**: đây là thứ cho phép attacker "tự do" mà nhãn vẫn độc lập |
| Cross-check `derived_probe_targets == generated` | `controlplane.py:283` | Chốt an toàn: phát hiện nếu bộ sinh và quan sát lệch nhau |
| Evidence hashed SHA256 + reset sạch (process chết) | `controlplane.py` | Giữ nguyên: tính tái lập + isolation |
| 4 dịch vụ blue không đọc `gold_truth` | `soc/workflow.py` | Chính là **quần thể blue** (đã có) |
| IR action deny-by-default, allowlist, approval, rollback, verify từ filesystem thật | `range/live/ir_actions.py`, `response/policy.py` | Khuôn cho "ngăn chặn" của blue |

**Hệ quả quan trọng:** attacker-agent không phải tính năng mới toàn phần. Hôm nay "attacker" là
hàm sinh plan cố định; ta nâng nó thành *agent chọn hành động trong allowlist*. Vì truth vẫn suy từ
hiệu ứng server-side, "sự tự do" của agent bị bao bởi tập hiệu ứng mà verifier hiểu được.

---

## 2. Luật bất biến — đọc trước khi thiết kế bất cứ gì

Năm luật dưới đây đến từ `CLAUDE.md`, `docs/BENCHMARK_PROTOCOL.md`, `docs/SECURITY.md`. Thiết kế
phải thỏa **toàn bộ**, nếu không nó không được coi là benchmark.

1. **Nhãn độc lập với agent.** Ground truth của một episode được suy từ quan sát phía server/host
   (log thật, trạng thái file thật, bảng tiến trình thật), *không* từ việc attacker khai nó đã làm
   gì, cũng *không* từ việc blue khai nó thấy gì. Agent là người điều khiển kịch bản, không phải
   người định nghĩa đáp án.
2. **Attacker chỉ chọn từ allowlist.** Mỗi họ hành động phải có: (a) cách thực thi inert/bounded
   trong lab, (b) **một verifier trạng thái độc lập** biết hiệu ứng thật của nó. Agent chọn *hành
   động nào, khi nào, bao nhiêu, theo thứ tự nào*; agent **không** được bịa ra loại hiệu ứng mà
   verifier không biết chấm.
3. **Isolation tuyệt đối.** Lab chạy `--network none` / `internal: true`, không ra internet thật,
   snapshot + rollback, tài sản lab-only có TTL. Không `sudo`, không mutate host thật, không tự
   `docker pull`/`run` (operator bấm tay). "Đăng nhập mạng xã hội / chơi game / lướt web thật" →
   **thay bằng dịch vụ mô phỏng trong lab**, không tài khoản thật, không internet.
4. **Fail closed + DEV_SIMULATION_ONLY.** Thiếu quyền/thiếu lab thật → `BLOCKED_INTEGRATION`. Mọi
   kết quả từ lab tự động mang nhãn `AUTOMATED_LAB_GROUND_TRUTH` (tier *thấp hơn* gold do chuyên
   gia ký). Không bịa telemetry.
5. **Không rò nhãn.** Blue không đọc `gold_truth`, không query log tương lai (`as_of` chặn ở
   gateway), không đọc episode khác. Attacker không được "mớm" nhãn vào kênh mà blue đọc.

---

## 3. Kiến trúc đề xuất

```
                      ┌─────────────────────── LAB CÔ LẬP (network none, snapshot) ───────────────────────┐
                      │                                                                                    │
  [CLIENT agents] ────┼──► dịch vụ in-lab (web giả, "social" giả, "game" giả, auth)  ──► LOG / STATE thật │
  (benign driver)     │           ▲                                                         │              │
                      │           │                                                         ▼              │
  [ATTACKER agents]───┼──► allowlist action (inert, bounded) ─────────────────────►  ⟨_derive_truth⟩      │
  (red driver)        │                                                            quan sát server-side    │
                      │                                                                     │ (sealed)     │
                      └─────────────────────────────────────────────────────────────────────┼─────────────┘
                                                                                             │
   episode RECORDED (trace + evidence hashed) + TRUTH SEALED  ◄───────────────────────────────┘
                                                                                             │
                                                                        ┌────────────────────┴───────────┐
                                                                        │  [BLUE agents] = thí sinh chấm  │
                                                                        │  MON / HUNT / IR / CNT          │
                                                                        │  chỉ đọc evidence, KHÔNG truth  │
                                                                        └────────────────────────────────┘
```

### 3.1 Client population (bộ sinh nhiễu lành tính)
- **Mục tiêu:** tạo hoạt động "người dùng bình thường" đủ thật để làm hard-negative cho blue (đo
  false-positive). Hôm nay đã có mầm mống: các `intent="benign"` + `_BENIGN_TRICKY` (SQL-word trong
  ngữ cảnh lành tính).
- **Hình thức:** client agent tương tác với **dịch vụ in-lab mô phỏng** — ví dụ một web app nhỏ,
  một "social" app loopback (đăng nhập/post/like), một "game server" loopback (join/score). Không
  internet, không tài khoản thật. Agent sinh đa dạng hành vi (giờ giấc, trình tự, lỗi gõ nhầm).
- **Chấm?** Không. Client **không phải thí sinh**. Nó chỉ sinh môi trường. Output của nó = log lành
  tính, đã biết trước là benign ở mức *episode* (vì verifier không quan sát thấy hiệu ứng độc hại).

### 3.2 Attacker population (red driver, bị chặn bởi allowlist)
- **Mục tiêu:** sinh các episode tấn công đa dạng hơn 3 kịch bản cứng hiện tại.
- **Cơ chế allowlist:** định nghĩa một **thư viện hành động** (`AttackAction`), mỗi hành động gồm
  `{id, execute(lab, params) -> inert/bounded, effect_verifier}`. Agent nhận một *mục tiêu trừu
  tượng* ("thử đạt được truy cập chưa phép vào webroot") và chọn chuỗi hành động **từ allowlist**.
  Agent **không** gọi shell tùy ý; nó chỉ phát ra action-id + tham số hợp lệ, control plane thực
  thi phần inert tương ứng.
- **Tại sao vẫn độc lập nhãn:** hiệu ứng được đo bởi `effect_verifier` đọc trạng thái thật (file
  xuất hiện có marker? số 401/user ≥ ngưỡng? tiến trình lab-only sinh ra?). Agent có "khai" gì cũng
  không đổi được truth.
- **Tính tái lập — điểm mấu chốt:** agent-driven ⇒ không tất định. Giải: **một lần chạy attacker
  agent sinh ra một episode; episode đó được RECORD (trace hành động + evidence hashed) và SEAL
  truth ngay lúc record.** Từ đó về sau episode là *cố định, replay được*; blue được chấm trên
  episode đã niêm phong. Attacker agent là **công cụ sinh/soạn kịch bản**, không nằm trong hệ được
  chấm. (So sánh: như một fuzzer sinh test-case; test-case đã lưu thì tất định.)
- **Seed & ngân sách:** mỗi lần sinh có seed + giới hạn số action, để tái tạo và chặn blow-up.

### 3.3 Blue population (thí sinh — đã có sẵn)
- Chính là `saber/soc/workflow.py`: MON (liệt kê dòng độc hại), HUNT (timeline + entity), IR (ngăn
  chặn reversible có approval), CNT (viết rule, test trên held-out).
- Mở rộng: cho phép cấu hình single-agent vs specialist vs multi-agent (đã có ở `soc eval`), để trả
  lời đúng câu hỏi nghiên cứu gốc: **phối hợp nhiều agent có hơn 1 agent / hơn rule truyền thống
  không**, dưới cùng ngân sách.
- Ràng buộc: không đọc `gold_truth`, không query tương lai, IR chỉ chạm tài sản lab-only qua
  approval + rollback.

---

## 4. Suy nhãn độc lập theo từng họ hành động (bảng khế ước)

Mỗi dòng là một "hợp đồng" attacker↔verifier. Allowlist khởi đầu = mở rộng 3 họ đã có, thêm vài họ
mới *chỉ khi* verifier độc lập tồn tại.

| Họ hành động | Thực thi inert trong lab | Hiệu ứng quan sát (NHÃN suy từ đây) | Hard negative lành tính |
|---|---|---|---|
| web probe (có sẵn) | GET chuỗi probe bất hoạt tới service loopback | tổ hợp token SQL trong log server | request chứa *từ* SQL, ngữ cảnh lành tính |
| brute force (có sẵn) | nhiều login sai tới /login loopback | số 401/user ≥ ngưỡng | 1 lần gõ nhầm (1×401) |
| fs change (có sẵn) | PUT file vào webroot sandbox | file server-side-script có marker trên đĩa | deploy script được phép (health.php…) |
| **(mới) tạo tiến trình bất thường** | spawn tiến trình lab-only từ allowlist | PID xuất hiện + parent/command khớp mẫu đã định | tác vụ admin hợp lệ cùng mẫu lệnh |
| **(mới) persistence giả** | ghi 1 entry vào "cron/registry" giả in-lab | entry xuất hiện ở store giả | thay đổi cấu hình được phép |
| **(mới) lateral giả** | mở kết nối tới host B *trong cùng lab* | log kết nối nội bộ server-side | kết nối dịch vụ nội bộ hợp lệ |

Quy tắc kết nạp một họ mới vào allowlist:
1. Thực thi được inert/bounded, không ra ngoài lab, có reset.
2. Có `effect_verifier` đọc trạng thái thật, không đọc nhãn sinh.
3. Có ≥1 hard-negative lành tính cùng "bề mặt" để precision của blue bị test thật.
4. Cross-check `derived == generated` pass (như `controlplane.py:283`).

> Lưu ý giữ đúng tinh thần `CLAUDE.md`: không tự `pull` image chứa công cụ tấn công, không chạy mã
> khai thác thật. "Attack" ở đây là **hiệu ứng mô phỏng inert trong lab của chính ta** đủ để blue
> phải phân biệt — không phải vũ khí hoá.

---

## 5. Chỉ số đo (đo blue, không đo "attacker thắng")

Theo `docs/BENCHMARK_PROTOCOL.md` (2 track):

- **Track A — Detection only:** TPR, FPR/precision, time-to-detect, chất lượng timeline/entity,
  chất lượng rule (CNT) trên held-out. Không thực thi containment.
- **Track B — Response enabled:** time-to-contain, tỉ lệ chặn thành công (verify từ trạng thái
  thật), **false containment** (chặn nhầm tài sản lành tính của client), **missed containment**,
  tác động lên dịch vụ client lành tính. Không phạt blue vì kỹ thuật mà attack *chưa kịp làm* do bị
  chặn sớm.
- **Tách reliability khỏi capability (blocker G-1):** episode `INVALID` (attack không chạy đúng,
  thiếu sensor, reset bẩn) bị loại khỏi mẫu số hiệu quả, không biến thành false-negative; nhưng vẫn
  vào báo cáo độ tin cậy.
- **Thống kê:** nhiều seed × nhiều họ; đơn vị thống kê là **episode/family**, không coi các log
  tương quan như quan sát độc lập; CI bootstrap theo cụm (đã có khuôn ở các report trước).

---

## 6. Cạm bẫy phải tránh (và cách thiết kế này tránh)

| Cạm bẫy | Vì sao chết người | Cách tránh trong thiết kế |
|---|---|---|
| Attacker tự khai "tôi đã chiếm quyền" → thành nhãn | Benchmark tự chấm theo lời agent | Nhãn chỉ từ `effect_verifier` server-side |
| Blue agent cũng là người sinh gold | Rò nhãn, vòng lặp tự xác nhận | Blue không bao giờ thấy `gold_truth`; truth seal trước khi blue chạy |
| Agent-driven ⇒ episode không tái lập | Không so sánh được cấu hình blue | Record + seal episode; blue chấm trên bản đã niêm phong |
| Attacker mạnh/yếu làm nhiễu độ khó | Lẫn "blue kém" với "attacker ngẫu nhiên dễ" | Attacker chỉ là generator; cố định tập episode rồi mới so blue |
| "Client lướt web thật" | Phá isolation, ra internet thật | Dịch vụ mô phỏng in-lab, network none |
| Tự coi kết quả lab = benchmark thật | Overclaim | Giữ nhãn `AUTOMATED_LAB_GROUND_TRUTH` < gold; tier không đổi |

---

## 7. Lộ trình đề xuất (mỗi mốc kiểm chứng được, dừng được)

- **H0 — operator chốt scope + bring-up lab.** Operator bấm `docker compose -f lab/docker-compose.yml
  up -d` (agent không tự bấm). Ingest telemetry benign để xác nhận đường ống thật chạy.
- **H1 — Client driver + record/seal cho 3 họ cũ (scripted-with-jitter). ✅ XONG.** `client_driver.py`
  sinh nhiễu benign có jitter (seeded), `run_episode(noise_clients=N)` phủ nhiễu bằng rng stream
  riêng; `record + seal` đã có sẵn trong `run_episode`; cross-check `derived == generated` pass;
  test chứng minh nhiễu giữ nguyên attack truth trên cả 4 họ. *Chưa LLM.*
- **H2 — Họ `persistence` mới (autostart/scheduled-task). ✅ XONG.** Endpoint `/cron/add` ghi store
  sandbox; `_derive_truth` suy nhãn từ marker trơ `LAB_AUTORUN_MARKER` trên đĩa (không chữ ký
  thật); scenario tất định với hard-negative = job hợp lệ (backup/logrotate/...); detector
  conventional khớp truth, naive over-flag; chạy qua workflow 4 dịch vụ. (Allowlist framework
  `AttackAction` tường minh: để H3.)
- **H3 — Blue chạy trên episode đã seal + Track A. ✅ XONG.** `attack_registry.py` (allowlist ↔
  verifier độc lập, test ép phủ đúng SCENARIOS) + `detect_bench.py` / `saber soc detect-bench`:
  conventional vs naive trên 4 họ × seed × nhiễu client, TP/FP/FN/TN vs truth niêm phong, CI
  bootstrap theo cụm (cụm = họ). Kết quả LIVE: conventional recall 1.0/precision 1.0/0 FP; naive
  precision 0.385/73 FP — **phân biệt được, không bão hoà trần**. **Track B** (`response_bench.py`
  / `saber soc response-bench`) chấm ngăn chặn thật trên fs_change: cả hai contain webshell
  (recall 1.0) nhưng naive gây 17 false-containment (quarantine nhầm file hợp lệ) vs conventional 0.
  Xem `docs/PHASE_H_REPORT.md`.
- **H4 — Scale + (tùy chọn) LLM sequencer.** Nhiều seed × 4 họ; tách reliability/capability (G-1);
  chỉ khi đó mới cân nhắc LLM-hóa driver và thêm họ `process`/`lateral`.

Mỗi mốc là một PR có test (positive, hard-negative, invalid/missing-data, cross-episode, leakage,
determinism của phần đã record) đúng checklist thẻ subtask.

---

## 8. Tác động tier (trung thực)

Hướng này **không tự động** nâng bài nào lên `READY_BENCHMARK`:
- Nhãn từ lab tự động là `AUTOMATED_LAB_GROUND_TRUTH`, **thấp hơn** gold do chuyên gia SOC/IR ký
  (blocker ED-1 vẫn mở).
- `READY_BENCHMARK` vẫn cần: lab được cấp phép + chuyên gia độc lập ký nhãn + holdout mù.
- Thành quả thực tế của hướng này: biến benchmark từ "ceiling-saturated, mọi cấu hình = 1.0" (kết
  luận Phase G) thành **bài đủ khó để phân biệt** rule vs single vs multi-agent — tức là làm cho câu
  hỏi nghiên cứu gốc *đo được*, chứ không phải tuyên bố đã đo xong.

---

## 9. Quyết định — ĐÃ CHỐT (operator, phiên này)

1. **Driver = scripted-with-jitter trước** cho cả client và attacker. Tất định, seeded, **không tốn
   quota subscription**, dễ kiểm chứng độc lập nhãn. Chỉ LLM-hóa sequencer sau khi đường ống đã chạy
   đúng. → Mốc H1–H3 không gọi LLM cho client/attacker.
2. **Allowlist action — tiêu chí "dễ + nhiều"**, chốt gói mốc đầu:
   - Biến **3 họ cũ** (`web_sqli_probe`, `auth_bruteforce`, `fs_change`) thành **driver-sequenced +
     record/seal** — công sức thấp, không cần verifier mới.
   - Thêm **1 họ mới: persistence giả** — store "autostart/cron" in-lab; nhãn = entry có marker;
     hard-neg = scheduled job hợp lệ. Công sức thấp (sao chép khuôn `fs_change`).
   - **Hoãn:** `process` bất thường (cần container Docker, trung bình) và `lateral` (cần host thứ 2,
     cao) — thêm sau khi khung 4 họ đã chạy.
3. **Client noise:** tái dùng service loopback hiện có là đủ cho mốc đầu; chưa dựng "social/game
   giả" cho tới khi cần đa dạng nhiễu hơn.
4. **Xác nhận tier:** hướng này land dưới `AUTOMATED_LAB_GROUND_TRUTH` / `DEV_SIMULATION_ONLY`,
   **không** claim `READY_BENCHMARK` (ED-1 vẫn mở).

---

## 10. Nhắc lại ranh giới một dòng

**Blue = thí sinh được chấm. Client + Attacker = bộ sinh môi trường. Nhãn = hiệu ứng thật quan sát
phía server, không bao giờ là lời của agent.** Giữ được dòng này thì mở rộng bao nhiêu cũng an toàn;
phá nó thì dù code đẹp đến đâu cũng không còn là benchmark.
