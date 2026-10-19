# Domain backlog — 55 NICE tasks / 175 subtasks

Mã T####.NNN là **đơn vị benchmark nghiệp vụ**. Mã T001–T038 trong engineering backlog là PR phát triển hệ thống, không thay thế danh mục này.

Dùng `python scripts/show_subtask.py T1112.001` hoặc mở `tasks/subtasks/T1112.001.md` để giao Claude Code một bài.

## MON — Vận hành giám sát ATTT 24/7 (16 NICE; 58 subtasks)

### T1085 — Nhận diện các mối đe dọa tiềm tàng đối với tài nguyên mạng

**Source review:** Chuẩn nghiệp vụ. Chưa có chiến lược benchmark phù hợp.

| Subtask | Môi trường | Mô tả nghiệp vụ nguồn (tóm tắt) | Scorer nguồn |
|---|---|---|---|
| [T1085.001](subtasks/T1085.001.md) | file | Cho 1 file log firewall N host, M host bị dò quét cổng, liệt kê các host bị dò quét | max(0, M′/M − N′/(N′+M′)) |
| [T1085.002](subtasks/T1085.002.md) | file | Thêm danh mục tài sản, phải xếp hạng tài sản theo mức đe doạ | 0.7·F2 + 0.3·max(0, ρ) |
| [T1085.003](subtasks/T1085.003.md) | soc | Log 7 ngày đa nguồn của 40 tài sản, phải nối được các cảnh báo rời rạc về cùng một chiến dịch. Bẫy FP: 4 tài sản bị scanner nội bộ quét hợp lệ | (0.6·F2 + 0.2·ρ + 0.2·e) × CITE |

### T1112 — Kiểm chứng cảnh báo mạng

**Source review:** Cần có benchmark check riêng cho sản phẩm VCS.

| Subtask | Môi trường | Mô tả nghiệp vụ nguồn (tóm tắt) | Scorer nguồn |
|---|---|---|---|
| [T1112.001](subtasks/T1112.001.md) | file | Cho 1 cảnh báo kèm file bị cảnh báo, trả lời cảnh báo đúng hay sai (TP/FP) | [verdict] |
| [T1112.002](subtasks/T1112.002.md) | file | Thêm log thô ±60 phút, phải nêu rule nào bắn và trên asset nào | Σ wᵢ·sᵢ |
| [T1112.003](subtasks/T1112.003.md) | soc | Cho trọn case SIEM, xác thực *claim* của cảnh báo. Đã có T1112_0001 | Σ wᵢ·sᵢ ; cap 0.30 nếu classification sai |

### T1241 — Ghi nhận các sự cố an ninh mạng

**Source review:** Benchmark chưa sát thực tế lắm. Công việc này là của đội Giám sát ATTT 24/7.

| Subtask | Môi trường | Mô tả nghiệp vụ nguồn (tóm tắt) | Scorer nguồn |
|---|---|---|---|
| [T1241.001](subtasks/T1241.001.md) | file | Cho 1 hồ sơ case bị xoá M trường bắt buộc, liệt kê các trường còn thiếu | max(0, M′/M − N′/(N′+M′)) |
| [T1241.002](subtasks/T1241.002.md) | file | Cho case đã xoá kết luận + SOP, điền loại sự cố và mức độ vào phiếu ticket | Σ wᵢ·sᵢ |
| [T1241.003](subtasks/T1241.003.md) | soc | Điền trọn phiếu ticket. 1/3 số case thuộc loại chưa có hướng dẫn → nhãn là gán Tier 3 | Σ wᵢ·sᵢ |

### T1242 — Chuyển cấp xử lý các sự cố có thể gây tác động tức thời và kéo dài tới môi trường

**Source review:** Benchmark chưa sát thực tế lắm. Công việc này là của đội Giám sát ATTT 24/7.

| Subtask | Môi trường | Mô tả nghiệp vụ nguồn (tóm tắt) | Scorer nguồn |
|---|---|---|---|
| [T1242.001](subtasks/T1242.001.md) | file | Cho 1 case cắt tại mốc Tier 1 kết thúc, trả lời leo thang hay tự khép | [decision] |
| [T1242.002](subtasks/T1242.002.md) | file | Thêm ma trận severity, phải chọn cả tier đích | Σ wᵢ·sᵢ |
| [T1242.003](subtasks/T1242.003.md) | soc | Thêm bảng cam kết SLA, phải tính cả hạn escalate. Trộn 50/50 case leo thang và case tự khép | Σ wᵢ·sᵢ ; báo riêng under/over-escalation |

### T1290 — Truyền đạt báo cáo sự kiện và hoạt động mạng hằng ngày

**Source review:** Chuẩn nghiệp vụ — mô tả đúng.

| Subtask | Môi trường | Mô tả nghiệp vụ nguồn (tóm tắt) | Scorer nguồn |
|---|---|---|---|
| [T1290.001](subtasks/T1290.001.md) | file | Cho 1 file CSV alert 30 ngày, tính 5 con số của báo cáo tháng | (số ô đúng)/5 |
| [T1290.002](subtasks/T1290.002.md) | file | Thêm dữ liệu case, phải tính % xử lý đúng hạn và chỉ ra top-5 rule nhiễu | Σ wᵢ·sᵢ |
| [T1290.003](subtasks/T1290.003.md) | soc | Trọn bộ số liệu báo cáo tháng từ dữ liệu thô. Verifier tự tính lại toàn bộ rồi so | Σ wᵢ·sᵢ |

### T1299 — Xác định nguyên nhân của cảnh báo mạng

**Source review:** Công việc của đội Giám sát ATTT 24/7. Cần có benchmark riêng cho sản phẩm VCS.

| Subtask | Môi trường | Mô tả nghiệp vụ nguồn (tóm tắt) | Scorer nguồn |
|---|---|---|---|
| [T1299.001](subtasks/T1299.001.md) | file | Cho cây tiến trình của 1 máy, chỉ ra tiến trình khởi nguồn chuỗi | [root_process] |
| [T1299.002](subtasks/T1299.002.md) | file | Thêm log thô, phải nêu thời điểm và cơ chế làm rule khớp | Σ wᵢ·sᵢ |
| [T1299.003](subtasks/T1299.003.md) | soc | Dựng lại trọn chuỗi nhân quả. Đã có T1299_0001 | Σ wᵢ·sᵢ ; cap 0.30 nếu classification sai |

### T1347 — Phát hiện các cuộc tấn công và xâm nhập an ninh mạng

**Source review:** OK — nghiệp vụ chuẩn. Cần có benchmark riêng cho sản phẩm VCS.

| Subtask | Môi trường | Mô tả nghiệp vụ nguồn (tóm tắt) | Scorer nguồn |
|---|---|---|---|
| [T1347.001](subtasks/T1347.001.md) | file | Cho 1 file log web N dòng, M dòng là request khai thác, liệt kê các dòng khai thác | max(0, M′/M − N′/(N′+M′)) |
| [T1347.002](subtasks/T1347.002.md) | file | Thêm log AD, phải gán nhóm hành vi trong danh mục giám sát | Σ wᵢ·sᵢ |
| [T1347.003](subtasks/T1347.003.md) | soc | Gói cảnh báo đa nguồn 1 khung giờ, mọi khẳng định phải kèm trích dẫn grep được | Σ wᵢ·sᵢ |

### T1348 — Phân biệt giữa hoạt động lành tính và các cuộc tấn công, xâm nhập có khả năng độc hại

**Source review:** OK — tag và mô tả nghiệp vụ chuẩn.

| Subtask | Môi trường | Mô tả nghiệp vụ nguồn (tóm tắt) | Scorer nguồn |
|---|---|---|---|
| [T1348.001](subtasks/T1348.001.md) | file | Cho danh sách N tiến trình, M tiến trình nguỵ trang tên hệ thống (svch0st.exe giả svchost.exe), liệt kê các tiến trình giả mạo | max(0, M′/M − N′/(N′+M′)) |
| [T1348.002](subtasks/T1348.002.md) | file | Thêm whitelist nội bộ, gán nhãn hợp lệ / tấn công cho từng hoạt động quản trị | accuracy |
| [T1348.003](subtasks/T1348.003.md) | soc | Phân tầng theo loại hoạt động (PsExec · WMI · PowerShell remoting · script hàng loạt · tác vụ định kỳ) để lớp đa số không kéo điểm. Đã có T134… | macro-average accuracy trên 5 tầng |
| [T1348.004](subtasks/T1348.004.md) | soc | Cảnh báo nhóm **Mã độc** (MALWARE): phân biệt lành tính hay độc hại dựa trên hash + nội dung file, không dừng ở tên phát hiện của AV. Mẫu âm b… | (0.35·s₁ + 0.25·s₂ + Σ mục riêng) × CITE |
| [T1348.005](subtasks/T1348.005.md) | soc | Cảnh báo nhóm **Email phishing / lộ lọt tài khoản** (PHISHING_EMAIL): phân biệt lành tính hay độc hại dựa trên header/URL email + có click khô… | (0.35·s₁ + 0.25·s₂ + Σ mục riêng) × CITE |
| [T1348.006](subtasks/T1348.006.md) | soc | Cảnh báo nhóm **Scan port** (PORT_SCAN): phân biệt lành tính hay độc hại dựa trên nguồn quét có nằm trong danh mục scanner/whitelist và đúng l… | (0.35·s₁ + 0.25·s₂ + Σ mục riêng) × CITE |
| [T1348.007](subtasks/T1348.007.md) | soc | Cảnh báo nhóm **Scan, khai thác lỗ hổng phần mềm** (VULN_EXPLOIT): phân biệt lành tính hay độc hại dựa trên payload trong PCAP + phiên bản trê… | (0.35·s₁ + 0.25·s₂ + Σ mục riêng) × CITE |
| [T1348.008](subtasks/T1348.008.md) | soc | Cảnh báo nhóm **Khai thác lỗ hổng ứng dụng web** (WEB_APP_EXPLOIT): phân biệt lành tính hay độc hại dựa trên mã HTTP trả về + file/DB có thay … | (0.35·s₁ + 0.25·s₂ + Σ mục riêng) × CITE |
| [T1348.009](subtasks/T1348.009.md) | soc | Cảnh báo nhóm **Credential** (CREDENTIAL_ACCESS): phân biệt lành tính hay độc hại dựa trên chuỗi 4625→4624 / truy cập lsass + tài khoản có đặc… | (0.35·s₁ + 0.25·s₂ + Σ mục riêng) × CITE |
| [T1348.010](subtasks/T1348.010.md) | soc | Cảnh báo nhóm **Net IOC** (NET_IOC): phân biệt lành tính hay độc hại dựa trên chất lượng IOC + tiến trình nào mở kết nối + có beacon/truyền dữ… | (0.35·s₁ + 0.25·s₂ + Σ mục riêng) × CITE |
| [T1348.011](subtasks/T1348.011.md) | soc | Cảnh báo nhóm **Tunneling** (TUNNELING): phân biệt lành tính hay độc hại dựa trên độ dài/entropy truy vấn + lưu lượng ra + tiến trình tạo kênh… | (0.35·s₁ + 0.25·s₂ + Σ mục riêng) × CITE |
| [T1348.012](subtasks/T1348.012.md) | soc | Cảnh báo nhóm **Persistence** (PERSISTENCE): phân biệt lành tính hay độc hại dựa trên mục khởi động + binary nó trỏ tới + tiến trình đã tạo ra… | (0.35·s₁ + 0.25·s₂ + Σ mục riêng) × CITE |
| [T1348.013](subtasks/T1348.013.md) | soc | Cảnh báo nhóm **Lateral movement** (LATERAL_MOVEMENT): phân biệt lành tính hay độc hại dựa trên logon type 3/10 + công cụ thực thi + nguồn có … | (0.35·s₁ + 0.25·s₂ + Σ mục riêng) × CITE |

### T1349 — Truyền đạt các cảnh báo về tấn công và xâm nhập an ninh mạng

**Source review:** Task về thông báo cho khách hàng và đội xử lý sự cố khi có sự cố. Chưa rõ hành động này có cần benchmark hay không.

| Subtask | Môi trường | Mô tả nghiệp vụ nguồn (tóm tắt) | Scorer nguồn |
|---|---|---|---|
| [T1349.001](subtasks/T1349.001.md) | file | Cho 1 case mức X và bảng RASCI, liệt kê đầu mối phải báo | F1 |
| [T1349.002](subtasks/T1349.002.md) | file | Thêm bảng SLA, phải chọn đúng kênh và mốc phải gửi | F1 × [channel] × [deadline] |
| [T1349.003](subtasks/T1349.003.md) | soc | Bằng chứng có lẫn tài sản của khách hàng khác — báo nhầm sang đầu mối khách kia thì 0 điểm | F1 × [channel] × [deadline] × [không báo nhầm khách khác] |

### T1350 — Thực hiện giám sát liên tục hoạt động của hệ thống

**Source review:** OK về nghiệp vụ. Tuy nhiên bài benchmark có vấn đề, không liên quan lắm (đang để màu vàng).

| Subtask | Môi trường | Mô tả nghiệp vụ nguồn (tóm tắt) | Scorer nguồn |
|---|---|---|---|
| [T1350.001](subtasks/T1350.001.md) | file | Cho 1 file log liên tục có 1 khoảng bị mất, chỉ ra khoảng mất log | [log_gap] |
| [T1350.002](subtasks/T1350.002.md) | file | Thêm luồng cảnh báo 1 ca trực 8 giờ, phải xếp hàng đợi xử lý | 0.6·ρ + 0.4·[log_gap] |
| [T1350.003](subtasks/T1350.003.md) | soc | Thêm ma trận + SLA: mọi case Nghiêm trọng/Cao phải nằm trong nhóm xử lý ≤ 30 phút | 0.6·ρ·[SLA] + 0.4·[log_gap] |

### T1351 — Xác định tác động của hoạt động độc hại tới hệ thống và thông tin

**Source review:** OK — tag và mô tả nghiệp vụ chuẩn.

| Subtask | Môi trường | Mô tả nghiệp vụ nguồn (tóm tắt) | Scorer nguồn |
|---|---|---|---|
| [T1351.001](subtasks/T1351.001.md) | file | Cho 1 sự cố và ma trận severity của khách hàng, chấm mức Nghiêm trọng/Cao/Trung bình/Thấp | [severity] |
| [T1351.002](subtasks/T1351.002.md) | file | Phải chỉ ra cả ô ma trận đã dùng — đúng mức mà sai ô là đoán trúng, không phải suy ra | [severity] × (1.0 nếu ô đúng, 0.5 nếu sai ô) |
| [T1351.003](subtasks/T1351.003.md) | soc | Thêm phạm vi ảnh hưởng và nguy cơ dữ liệu. Phủ đủ 4 mức + ô biên máy VIP, hệ thống cấp 3 | (Σ wᵢ·sᵢ) × [matrix_cell] |

### T1386 — Phân tích các bất thường trong lưu lượng mạng

**Source review:** Chuẩn nghiệp vụ. Tuy nhiên bài benchmark chưa sát thực tế (đang để màu vàng).

| Subtask | Môi trường | Mô tả nghiệp vụ nguồn (tóm tắt) | Scorer nguồn |
|---|---|---|---|
| [T1386.001](subtasks/T1386.001.md) | file | Cho 1 file conn.log N kết nối, M kết nối là beacon C2, liệt kê các kết nối C2 | max(0, M′/M − N′/(N′+M′)) |
| [T1386.002](subtasks/T1386.002.md) | file | Thêm netconn từ endpoint, phải chỉ đúng tiến trình mở kết nối | F1 (sai tiến trình = 0.5 phần tử) |
| [T1386.003](subtasks/T1386.003.md) | soc | NetFlow 14 ngày cả dải mạng. Mẫu âm bắt buộc là lưu lượng nền **cũng có chu kỳ đều** (NTP, telemetry, health-check) | Σ wᵢ·sᵢ |

### T1387 — Thẩm định các cảnh báo của hệ thống phát hiện xâm nhập (IDS)

**Source review:** OK về nghiệp vụ, nhưng benchmark chưa sát thực tế → đổi sang vàng.

| Subtask | Môi trường | Mô tả nghiệp vụ nguồn (tóm tắt) | Scorer nguồn |
|---|---|---|---|
| [T1387.001](subtasks/T1387.001.md) | file | Cho 1 cảnh báo IDS và PCAP của chính phiên đó, trả lời TP hay FP | [verdict] |
| [T1387.002](subtasks/T1387.002.md) | file | Phải chỉ ra khoảng byte nào trong payload làm chữ ký khớp | Σ wᵢ·sᵢ |
| [T1387.003](subtasks/T1387.003.md) | soc | Thêm sơ đồ mạng có NAT: phải truy đúng IP nguồn thật và chấm lại severity theo vai trò máy đích | Σ wᵢ·sᵢ |

### T1388 — Cô lập malware

**Source review:** Chuẩn nghiệp vụ. Chưa có bài benchmark.

| Subtask | Môi trường | Mô tả nghiệp vụ nguồn (tóm tắt) | Scorer nguồn |
|---|---|---|---|
| [T1388.001](subtasks/T1388.001.md) | file | Cho 1 máy nhiễm và danh mục tài sản có đánh dấu máy VIP, chọn lớp cô lập | [layer] × [không cô lập máy VIP] |
| [T1388.002](subtasks/T1388.002.md) | file | Phải nộp cả chuỗi hành động cô lập kèm lớp thực thi | F1 × [VIP] |
| [T1388.003](subtasks/T1388.003.md) | soc | Ba ràng buộc cứng, vi phạm bất kỳ cái nào thì 0 toàn bài: cô lập máy VIP · cô lập trước khi thu ảnh bộ nhớ · chặn dải chứa hệ thống cấp 3 | F1 × Π[3 ràng buộc cứng] |

### T1389 — Loại bỏ malware

**Source review:** Chuẩn nghiệp vụ.

| Subtask | Môi trường | Mô tả nghiệp vụ nguồn (tóm tắt) | Scorer nguồn |
|---|---|---|---|
| [T1389.001](subtasks/T1389.001.md) | vm | Cho 1 máy ảo N file, M file mã độc, xoá toàn bộ M file và không xoá file sạch thì được 1/1 điểm | [M biến mất] × [N nguyên byte] |
| [T1389.002](subtasks/T1389.002.md) | vm | Mã độc có cơ chế tự phục hồi (cron + systemd + profile.d) — phải gỡ cả kênh khôi phục | Π[3 điều kiện] |
| [T1389.003](subtasks/T1389.003.md) | vm | Verifier quét **toàn máy** theo content hash để chặn việc agent chỉ di chuyển file đi nơi khác | Π[4 điều kiện] |

### T1428 — Thông báo cho quản lý được chỉ định, đội ứng cứu sự cố và nhân sự nhà cung cấp dịch vụ an ninh mạng về các sự cố an ninh mạng nghi ngờ

**Source review:** Chuẩn nghiệp vụ. Chưa có hướng benchmark.

| Subtask | Môi trường | Mô tả nghiệp vụ nguồn (tóm tắt) | Scorer nguồn |
|---|---|---|---|
| [T1428.001](subtasks/T1428.001.md) | file | Cho 1 case mức X và bảng cam kết SLA, trả lời mốc phải thông báo | [deadline] |
| [T1428.002](subtasks/T1428.002.md) | file | Thêm danh mục tài sản, phải liệt kê đầu mối theo RASCI | F1 × [deadline] |
| [T1428.003](subtasks/T1428.003.md) | soc | Bài tuân thủ quy tắc thuần tuý nên chạy lặp 5 lần trên cùng đề để đo độ ổn định | F1 × [channel] × [deadline] ; chạy lặp 5 lần, báo thêm độ lệch |

## CNT — Tối ưu ATTT — Content Security (5 NICE; 15 subtasks)

### T0020 — Xây dựng nội dung (rule/chữ ký) cho công cụ phòng thủ mạng

**Source review:** Task riêng của team Content Security → tag chỉ còn `cs`. Benchmark cần check thêm cả content liên quan tới các sản phẩm của VCS.

| Subtask | Môi trường | Mô tả nghiệp vụ nguồn (tóm tắt) | Scorer nguồn |
|---|---|---|---|
| [T0020.001](subtasks/T0020.001.md) | file | Cho 1 file log N dòng, M dòng là kỹ thuật cần bắt, viết 1 regex/rule — verifier chạy rule rồi đếm | max(0, M′/M − N′/(N′+M′)) |
| [T0020.002](subtasks/T0020.002.md) | soc | Viết theo chuẩn rule của SIEM đích và gán mapping ATT&CK | Σ wᵢ·sᵢ |
| [T0020.003](subtasks/T0020.003.md) | soc | Corpus 200.000 dòng đã gán nhãn (P = 50 sự kiện dương), nền chọn loại dễ khớp nhầm. Rule không parse hoặc timeout → 0 | max(0, TPR − FPR) × [parse_ok] |

### T1384 — Thiết lập các quy trình về tập hành vi xâm nhập (intrusion set)

**Source review:** Nôm na: từ hiểu biết về một nhóm tấn công (họ hay dùng kỹ thuật gì, tool gì, hạ tầng nào), team xây dựng các bước lặp lại được để nhận diện và truy vết đúng nhóm đó mỗi khi nó xuất hiện. Có nghiệp vụ này; chưa có hướng benchmark như thế nào.

| Subtask | Môi trường | Mô tả nghiệp vụ nguồn (tóm tắt) | Scorer nguồn |
|---|---|---|---|
| [T1384.001](subtasks/T1384.001.md) | file | Cho danh sách rule hiện có và 1 technique ATT&CK, trả lời technique đó đã được phủ chưa | [covered] |
| [T1384.002](subtasks/T1384.002.md) | file | Cho cả intrusion set, liệt kê technique nào chưa được rule nào phủ | F1 |
| [T1384.003](subtasks/T1384.003.md) | soc | Xây use-case hunting có truy vấn chạy được. Cấy 1 đề thiếu hẳn nguồn log → đáp án đúng là "không đủ dữ liệu", không phải "không có dấu vết" | Σ wᵢ·sᵢ |

### T1406 — Xây dựng chữ ký cho công cụ phòng thủ mạng

**Source review:** Task của team Content Security → tag chỉ còn `cs`. Cần bổ sung benchmark liên quan tới sản phẩm VCS.

| Subtask | Môi trường | Mô tả nghiệp vụ nguồn (tóm tắt) | Scorer nguồn |
|---|---|---|---|
| [T1406.001](subtasks/T1406.001.md) | file | Cho M mẫu cùng họ và N mẫu sạch, viết 1 luật YARA — verifier chạy luật trên cả hai tập | F1 |
| [T1406.002](subtasks/T1406.002.md) | file | Nửa tập dương là biến thể **đã đổi hash nhưng giữ hành vi** — luật bắt bằng hash tự rớt recall xuống 0.5 | F1 |
| [T1406.003](subtasks/T1406.003.md) | soc | Đầu vào là PCAP, sinh chữ ký Suricata / parser cho hệ thống nội bộ của khách hàng | F1 |

### T1111 — Quản lý cập nhật rule và chữ ký cho các ứng dụng phòng thủ mạng chuyên dụng

**Source review:** Có nghiệp vụ. Bổ sung tag Giám sát 24/7 (`mon`) và Xử lý sự cố (`ir`) cùng Content Security.

| Subtask | Môi trường | Mô tả nghiệp vụ nguồn (tóm tắt) | Scorer nguồn |
|---|---|---|---|
| [T1111.001](subtasks/T1111.001.md) | file | Cho 1 rule và N alert nó sinh ra, M alert là FP, viết điều kiện lọc — verifier áp lại lên log | max(0, ΔFP% − ΔTP_mất%) |
| [T1111.002](subtasks/T1111.002.md) | file | Phải chẩn đoán nguyên nhân FP: do logic rule, do dữ liệu, hay do thay đổi môi trường | Σ wᵢ·sᵢ |
| [T1111.003](subtasks/T1111.003.md) | soc | Giảm FP 80% mà mất 10% TP được 0.70; mất bất kỳ TP mức Nghiêm trọng/Cao nào → 0 | max(0, ΔFP% − ΔTP_mất%) × [không mất TP Nghiêm trọng/Cao] |

### T1644 — Xây dựng các chỉ dấu cho tác chiến mạng

**Source review:** OK — tag và mô tả nghiệp vụ chuẩn.

| Subtask | Môi trường | Mô tả nghiệp vụ nguồn (tóm tắt) | Scorer nguồn |
|---|---|---|---|
| [T1644.001](subtasks/T1644.001.md) | file | Cho 1 báo cáo TI, trích toàn bộ IOC — chuẩn hoá defang, lowercase trước khi so | F1 macro theo loại IOC |
| [T1644.002](subtasks/T1644.002.md) | file | Phải phân loại IOC theo độ bền (hash đổi được / domain đổi được / TTP khó đổi) | Σ wᵢ·sᵢ |
| [T1644.003](subtasks/T1644.003.md) | soc | Chuyển IOC thành rule chạy được. Nặng tay về phía rule vì chép bảng IOC là việc máy làm được | Σ wᵢ·sᵢ |

## HUNT — Threat Hunt (13 NICE; 39 subtasks)

### T0292 — Khuyến nghị các biện pháp khắc phục lỗ hổng cho môi trường máy tính

**Source review:** OK — tag và mô tả nghiệp vụ chuẩn.

| Subtask | Môi trường | Mô tả nghiệp vụ nguồn (tóm tắt) | Scorer nguồn |
|---|---|---|---|
| [T0292.001](subtasks/T0292.001.md) | file | Cho 1 ticket lỗ hổng, trả lời mức ưu tiên khắc phục | [priority] |
| [T0292.002](subtasks/T0292.002.md) | file | Thêm sơ đồ mạng: lỗ hổng CVSS 9.8 nhưng không phơi ra ngoài thì ưu tiên đúng là Thấp | Σ wᵢ·sᵢ |
| [T0292.003](subtasks/T0292.003.md) | soc | Thêm log lịch sử: phải trả lời lỗ hổng đã bị khai thác trước khi vá chưa, kèm dẫn chứng grep được | (Σ wᵢ·sᵢ) với exploited nhân CITE |

### T0167 — Thực hiện phân tích chữ ký tệp

**Source review:** Benchmark không chuẩn. Khó benchmark cho task này.

| Subtask | Môi trường | Mô tả nghiệp vụ nguồn (tóm tắt) | Scorer nguồn |
|---|---|---|---|
| [T0167.001](subtasks/T0167.001.md) | file | Cho danh sách N file kèm hash và 1 bảng IOC, liệt kê các file khớp IOC | max(0, M′/M − N′/(N′+M′)) |
| [T0167.002](subtasks/T0167.002.md) | file | Phán quyết độc hại / lành tính cho từng file. Mẫu âm: file sạch dùng eval/base64 hợp lệ (template engine, minifier, packer thương mại) | accuracy |
| [T0167.003](subtasks/T0167.003.md) | file | Thêm nhãn họ mã độc, so theo bảng alias vì mỗi hãng đặt tên khác nhau | Σ wᵢ·sᵢ |

### T1102 — Phát hiện các vụ xâm nhập

**Source review:** OK — tag và mô tả nghiệp vụ chuẩn.

| Subtask | Môi trường | Mô tả nghiệp vụ nguồn (tóm tắt) | Scorer nguồn |
|---|---|---|---|
| [T1102.001](subtasks/T1102.001.md) | file | Cho bản trích artifact của N máy, M máy có dấu vết xâm nhập, liệt kê các máy bị xâm nhập | F2 |
| [T1102.002](subtasks/T1102.002.md) | file | Thêm 1 máy **chỉ còn dấu vết quá khứ**: file đã bị xoá, chỉ còn log AV và prefetch | F2 |
| [T1102.003](subtasks/T1102.003.md) | vm | Môi trường 12 máy, bắt buộc có ≥ 2 máy sạch nhiều nhiễu (phần mềm quản trị, agent backup) | F2 × CITE |

### T1103 — Phân tích các vụ xâm nhập

**Source review:** OK — tag và mô tả nghiệp vụ chuẩn.

| Subtask | Môi trường | Mô tả nghiệp vụ nguồn (tóm tắt) | Scorer nguồn |
|---|---|---|---|
| [T1103.001](subtasks/T1103.001.md) | file | Cho 20 sự kiện của 1 cuộc tấn công bị xáo trộn, sắp lại theo đúng giai đoạn Kill Chain | Kendall tau |
| [T1103.002](subtasks/T1103.002.md) | file | Phải gán tên giai đoạn Kill Chain cho từng sự kiện | Σ wᵢ·sᵢ |
| [T1103.003](subtasks/T1103.003.md) | soc | Trọn hiện vật 1 case đã khép trừ kết luận, kể cả ảnh bộ nhớ. Mốc lệch quá ±5 phút tính sai | Σ wᵢ·sᵢ ; timeline = 0.5·τ + 0.5·recall mốc |

### T1104 — Ghi nhận những gì đã biết về các vụ xâm nhập

**Source review:** OK — tag và mô tả nghiệp vụ chuẩn.

| Subtask | Môi trường | Mô tả nghiệp vụ nguồn (tóm tắt) | Scorer nguồn |
|---|---|---|---|
| [T1104.001](subtasks/T1104.001.md) | file | Cho 1 gói bằng chứng, điền 6 trường bắt buộc của Technical Report | (số trường đúng)/6 |
| [T1104.002](subtasks/T1104.002.md) | file | Mỗi trường phải kèm trích dẫn {hiện vật, định vị, trích} để verifier grep lại | Σ wᵢ·sᵢ |
| [T1104.003](subtasks/T1104.003.md) | file | Technical Report đầy đủ theo schema của HV-33. Không có ô nào cần người đọc | Σ wᵢ·sᵢ |

### T1381 — Quét virus trên các vật chứa dữ liệu số

**Source review:** Quét thiết bị (USB, ổ cứng…) — VCS có thực hiện. Đề xuất benchmark: input là thiết bị, output là thiết bị có sạch mã độc hay không.

| Subtask | Môi trường | Mô tả nghiệp vụ nguồn (tóm tắt) | Scorer nguồn |
|---|---|---|---|
| [T1381.001](subtasks/T1381.001.md) | file | Cho danh sách N file kèm hash, M file mã độc, liệt kê các file mã độc | F1 |
| [T1381.002](subtasks/T1381.002.md) | vm | Môi trường máy ảo, agent quét và báo cáo, không được để lại dấu vết trên máy khách | F1 × [máy không đổi] |
| [T1381.003](subtasks/T1381.003.md) | vm | Thêm họ mã độc và phạm vi ảnh hưởng, đúng đầu ra của một đợt quét Viettel Scanner | (Σ wᵢ·sᵢ) × [máy không đổi] |

### T1487 — Giám sát tệp và registry trên các hệ thống đang chạy

**Source review:** Chuẩn nghiệp vụ, nhưng chưa có bài benchmark.

| Subtask | Môi trường | Mô tả nghiệp vụ nguồn (tóm tắt) | Scorer nguồn |
|---|---|---|---|
| [T1487.001](subtasks/T1487.001.md) | vm | Cho 1 máy ảo N file, M file mã độc, thống kê các file nghi ngờ | max(0, M′/M − N′/(N′+M′)) |
| [T1487.002](subtasks/T1487.002.md) | vm | Thêm mục persistence hệ thống (cron.d, systemd, profile.d, Run key) trộn với mục hợp lệ (certbot, logrotate, backup-db) | Σ wᵢ·sᵢ, mỗi mục theo max(0, M′/M − N′/(N′+M′)) |
| [T1487.003](subtasks/T1487.003.md) | vm | Thêm tiến trình đang chạy và whitelist nội bộ; agent quan sát, không được sửa máy | (Σ wᵢ·sᵢ) × [máy không đổi] |

### T0845 — Nhận diện các chiến thuật và phương thức của mối đe dọa mạng

**Source review:** OK — tag và mô tả nghiệp vụ chuẩn.

| Subtask | Môi trường | Mô tả nghiệp vụ nguồn (tóm tắt) | Scorer nguồn |
|---|---|---|---|
| [T0845.001](subtasks/T0845.001.md) | file | Cho 1 dòng lệnh, ánh xạ sang 1 technique ATT&CK | 1.0 đúng technique · 0.5 đúng tactic · 0 sai cả hai |
| [T0845.002](subtasks/T0845.002.md) | file | Cho chuỗi 10 hành vi, ánh xạ toàn bộ sang ATT&CK | macro-average (đúng technique 1.0 / đúng tactic 0.5) |
| [T0845.003](subtasks/T0845.003.md) | soc | Bắt buộc dẫn chứng từng technique, nếu không model liệt kê 30 technique là ăn hết recall | macro-average ; technique không grep được bằng chứng bị loại khỏi tử số |

### T1053 — Nhận diện và mô tả đặc điểm hoạt động xâm nhập nhằm vào một nạn nhân hoặc mục tiêu

**Source review:** Chuẩn nghiệp vụ.

| Subtask | Môi trường | Mô tả nghiệp vụ nguồn (tóm tắt) | Scorer nguồn |
|---|---|---|---|
| [T1053.001](subtasks/T1053.001.md) | file | Cho log xác thực N phiên, M phiên là di chuyển ngang, liệt kê cặp (máy nguồn → máy đích) | max(0, M′/M − N′/(N′+M′)) |
| [T1053.002](subtasks/T1053.002.md) | file | Thêm telemetry, phải tìm cả cơ chế duy trì truy cập | Σ wᵢ·sᵢ |
| [T1053.003](subtasks/T1053.003.md) | soc | Dựng chân dung xâm nhập đầy đủ trên case đã khép, cắt sạch phần kết luận | Σ wᵢ·sᵢ |

### T1341 — Thực hiện các cuộc rà soát theo yêu cầu

**Source review:** Tag `ca` chuẩn — đúng nghiệp vụ Compromised Assessment: rà soát cấu hình không an toàn và điểm yếu có thể bị lợi dụng xâm nhập (KeyWDigest, AccessibilityFeatures, IIS Machine Key đã lộ). Chưa có benchmark đo task này (tier none).

| Subtask | Môi trường | Mô tả nghiệp vụ nguồn (tóm tắt) | Scorer nguồn |
|---|---|---|---|
| [T1341.001](subtasks/T1341.001.md) | file | Cho 1 bản xuất cấu hình K mục, M mục không an toàn (WDigest bật, IIS Machine Key đã lộ), liệt kê | max(0, M′/M − N′/(N′+M′)) |
| [T1341.002](subtasks/T1341.002.md) | file | Thêm ma trận, phải xếp mức rủi ro cho từng cấu hình | Σ wᵢ·sᵢ |
| [T1341.003](subtasks/T1341.003.md) | vm | Môi trường máy ảo thật, agent **không được sửa máy** — verifier so SHA-256 cây cấu hình trước/sau | (Σ wᵢ·sᵢ) × [máy không đổi] |

### T2012 — Kiểm tra các kết nối mạng

**Source review:** Nên xếp vào nhóm Điều tra số (Forensics). Thiếu tag Xử lý sự cố → đã bổ sung `ir`. Benchmark chưa sát thực tế.

| Subtask | Môi trường | Mô tả nghiệp vụ nguồn (tóm tắt) | Scorer nguồn |
|---|---|---|---|
| [T2012.001](subtasks/T2012.001.md) | file | Cho output netstat N kết nối, M kết nối bất thường, liệt kê các kết nối bất thường | max(0, M′/M − N′/(N′+M′)) |
| [T2012.002](subtasks/T2012.002.md) | file | Thêm whitelist, phải chỉ đúng tiến trình mở kết nối — không biết tiến trình thì không chặn đúng chỗ | F1 (sai tiến trình = 0.5 phần tử) |
| [T2012.003](subtasks/T2012.003.md) | vm | Máy ảo đang chạy, K = 25 kết nối, M = 4 là C2/tunneling (reverse shell, DNS tunnel, ssh -R); agent tự chạy ss/lsof | F1 × [máy không đổi] |

### T2013 — Tìm các chỉ dấu của hoạt động xâm nhập

**Source review:** OK — tag và mô tả nghiệp vụ chuẩn.

| Subtask | Môi trường | Mô tả nghiệp vụ nguồn (tóm tắt) | Scorer nguồn |
|---|---|---|---|
| [T2013.001](subtasks/T2013.001.md) | file | Cho 1 file log thô, trích toàn bộ IOC — tính riêng từng loại rồi macro-average để loại hiếm không bị nuốt | F1 macro theo 6 loại IOC |
| [T2013.002](subtasks/T2013.002.md) | file | Cấy sẵn dấu vết xoá dấu vết: log 1102 bị xoá, EDR bị tắt, timestamp bị sửa lùi | Σ wᵢ·sᵢ |
| [T2013.003](subtasks/T2013.003.md) | soc | Hiện vật đa nguồn của trọn một đợt săn tìm | Σ wᵢ·sᵢ |

### T2016 — Xác định các khu vực đã bị xâm phạm

**Source review:** OK — tag và mô tả nghiệp vụ chuẩn.

| Subtask | Môi trường | Mô tả nghiệp vụ nguồn (tóm tắt) | Scorer nguồn |
|---|---|---|---|
| [T2016.001](subtasks/T2016.001.md) | file | Cho log xác thực, liệt kê các tài khoản đã bị chiếm quyền | F2 |
| [T2016.002](subtasks/T2016.002.md) | file | Thêm log biên, phải liệt kê cả máy bị xâm phạm | Σ wᵢ·sᵢ |
| [T2016.003](subtasks/T2016.003.md) | soc | Phải phân mức bị_kiểm_soát / bị_chạm / chỉ_bị_dò — hai mức đầu dẫn tới hai kế hoạch xử lý khác hẳn nhau | Σ wᵢ·sᵢ − 0.5 × (số phần tử xếp sai mức) |

## IR — Xử lý sự cố ATTT (21 NICE; 63 subtasks)

### T1391 — Tái dựng các cuộc tấn công độc hại

**Source review:** Task của team Xử lý sự cố (IR) → tag chỉ còn `ir`. Còn lại OK.

| Subtask | Môi trường | Mô tả nghiệp vụ nguồn (tóm tắt) | Scorer nguồn |
|---|---|---|---|
| [T1391.001](subtasks/T1391.001.md) | file | Cho log xác thực của nhiều máy, chỉ ra Patient Zero | [patient_zero] |
| [T1391.002](subtasks/T1391.002.md) | file | Phải vẽ cả bản đồ lây nhiễm, không chỉ điểm khởi đầu | Σ wᵢ·sᵢ |
| [T1391.003](subtasks/T1391.003.md) | soc | Cấy 1 máy có dấu vết **sớm hơn** nhưng do quét lỗ hổng hợp lệ, để bẫy việc chọn Patient Zero theo timestamp sớm nhất | Σ wᵢ·sᵢ ; cap 0.5 nếu sai Patient Zero |

### T0173 — Thực hiện phân tích dòng thời gian (timeline)

**Source review:** Công việc của team Xử lý sự cố (IR) → tag chỉ còn `ir`. Còn lại OK.

| Subtask | Môi trường | Mô tả nghiệp vụ nguồn (tóm tắt) | Scorer nguồn |
|---|---|---|---|
| [T0173.001](subtasks/T0173.001.md) | file | Cho 30 sự kiện ghi ở 3 múi giờ khác nhau, sắp lại theo thời gian thật | Kendall tau |
| [T0173.002](subtasks/T0173.002.md) | file | Phải chuẩn hoá mọi mốc về UTC, không chỉ sắp thứ tự | Σ wᵢ·sᵢ |
| [T0173.003](subtasks/T0173.003.md) | soc | 6 mốc bắt buộc: initial access · leo thang · lateral movement · persistence · exfil · phát hiện. Lệch quá ±5 phút tính sai | Σ wᵢ·sᵢ |

### T0182 — Thực hiện phân tích malware cấp 1, 2 và 3

**Source review:** OK — tag và mô tả nghiệp vụ chuẩn.

| Subtask | Môi trường | Mô tả nghiệp vụ nguồn (tóm tắt) | Scorer nguồn |
|---|---|---|---|
| [T0182.001](subtasks/T0182.001.md) | file | Cho 1 binary, trích 5 trường: tên hàm chính, hằng số, key, địa chỉ C2, thuật toán mã hoá — ghép thẳng bộ RE-Gen 24 độ khó × 10 mẫu của anh Quang | (số trường đúng)/5 |
| [T0182.002](subtasks/T0182.002.md) | file | Thêm phán quyết độc hại/lành tính và họ mã độc | Σ wᵢ·sᵢ |
| [T0182.003](subtasks/T0182.003.md) | file | Mẫu exe/dll/sys/pdf/docx/elf chạy trong sandbox, phải mô tả hành vi và trích IOC | Σ wᵢ·sᵢ |

### T0397 — Phân tích Windows registry

**Source review:** Benchmark không chuẩn. Khó benchmark cho task này.

| Subtask | Môi trường | Mô tả nghiệp vụ nguồn (tóm tắt) | Scorer nguồn |
|---|---|---|---|
| [T0397.001](subtasks/T0397.001.md) | file | Cho 1 file xuất registry K mục Run/Service/Task, M mục độc hại, liệt kê các mục độc hại | max(0, M′/M − N′/(N′+M′)) |
| [T0397.002](subtasks/T0397.002.md) | file | Phải phân đúng loại: run_key / service / scheduled_task / wmi / startup / systemd | F1 (đúng vị trí sai loại = 0.5 phần tử) |
| [T0397.003](subtasks/T0397.003.md) | vm | Môi trường máy ảo, K = 40 mục, M = 8 độc hại. Cấy 1 mục WMI Event Consumer — chỗ hầu hết công cụ bỏ sót | Σ wᵢ·sᵢ |

### T1090 — Xác định phương pháp tốt nhất để truy tìm thủ phạm của một vụ xâm nhập mạng

**Source review:** Nghiệp vụ OK, benchmark khá chuẩn → chuyển sang xanh. Dựa vào dấu hiệu đặc trưng (TTP/văn phong) của nhóm tấn công để xác định tên nhóm.

| Subtask | Môi trường | Mô tả nghiệp vụ nguồn (tóm tắt) | Scorer nguồn |
|---|---|---|---|
| [T1090.001](subtasks/T1090.001.md) | file | Cho 1 danh sách TTP, trả lời thuộc nhóm APT nào (bảng alias: APT41 = Winnti = Barium) | [apt_group] |
| [T1090.002](subtasks/T1090.002.md) | file | Bắt buộc có ≥ 2 mẫu mà đáp án đúng là khong_du_can_cu_quy_ket — quy kết bừa là rủi ro nghiệp vụ thật | [apt_group] |
| [T1090.003](subtasks/T1090.003.md) | file | Kết luận nhóm mà không nêu được TTP trùng khớp là đoán tên, không phải suy ra | Σ wᵢ·sᵢ ; cap 0.5 nếu tập TTP không giao với nhãn |

### T1253 — Thực hiện phân tích động trên các ổ đĩa

**Source review:** Chuẩn nghiệp vụ, nhưng chỉ của team Xử lý sự cố (IR) → tag chỉ còn `ir`.

| Subtask | Môi trường | Mô tả nghiệp vụ nguồn (tóm tắt) | Scorer nguồn |
|---|---|---|---|
| [T1253.001](subtasks/T1253.001.md) | file | Cho danh sách vùng nhớ của N tiến trình, M tiến trình bị inject, liệt kê các tiến trình bị inject | max(0, M′/M − N′/(N′+M′)) |
| [T1253.002](subtasks/T1253.002.md) | file | Phải nêu kỹ thuật inject. Mẫu âm: tiến trình hợp lệ có vùng nhớ RWX (JIT .NET/Java, trình duyệt) | Σ wᵢ·sᵢ |
| [T1253.003](subtasks/T1253.003.md) | file | Ảnh bộ nhớ thật, phải trích cả IOC chỉ tồn tại trong RAM | Σ wᵢ·sᵢ |

### T1323 — Phân tích lưu lượng mạng liên quan đến hoạt động độc hại

**Source review:** Nghiệp vụ OK. Benchmark nên là bài phân tích pcap (packet capture).

| Subtask | Môi trường | Mô tả nghiệp vụ nguồn (tóm tắt) | Scorer nguồn |
|---|---|---|---|
| [T1323.001](subtasks/T1323.001.md) | file | Cho 1 file PCAP, trích IOC (IP, domain, URL) của kênh độc hại | F1 |
| [T1323.002](subtasks/T1323.002.md) | file | Thêm flow, phải tách riêng đâu là kênh điều khiển | Σ wᵢ·sᵢ |
| [T1323.003](subtasks/T1323.003.md) | soc | Thang 3 mức đã_bị_trích_xuất / có_nguy_cơ / không_có_bằng_chứng — trong IR, "không loại trừ" là kết luận hợp lệ | Σ wᵢ·sᵢ |

### T1324 — Xử lý chứng cứ số

**Source review:** Nghiệp vụ OK, chỉ của team Xử lý sự cố (IR) → tag chỉ còn `ir`. Benchmark chưa chuẩn, cần chỉnh lại.

| Subtask | Môi trường | Mô tả nghiệp vụ nguồn (tóm tắt) | Scorer nguồn |
|---|---|---|---|
| [T1324.001](subtasks/T1324.001.md) | file | Cho danh sách 8 loại bằng chứng, sắp thứ tự thu thập theo độ dễ mất | Kendall tau |
| [T1324.002](subtasks/T1324.002.md) | file | Phải nêu cách bảo toàn từng loại bằng chứng | Σ wᵢ·sᵢ |
| [T1324.003](subtasks/T1324.003.md) | file | Order of volatility chuẩn: RAM → kết nối đang mở → tiến trình → disk → log tập trung. Checklist bắt buộc: hash từng tệp, biên bản thu giữ, chu… | Σ wᵢ·sᵢ ; cap 0.6 nếu thiếu 1 mục checklist |

### T1370 — Thu thập các dấu vết của vụ xâm nhập

**Source review:** OK — tag và mô tả nghiệp vụ chuẩn.

| Subtask | Môi trường | Mô tả nghiệp vụ nguồn (tóm tắt) | Scorer nguồn |
|---|---|---|---|
| [T1370.001](subtasks/T1370.001.md) | vm | Cho 1 máy ảo có M dấu vết, thu về /workspace/evidence/ mà không làm đổi hash và timestamp gốc | recall × [bằng chứng nguyên vẹn] |
| [T1370.002](subtasks/T1370.002.md) | vm | Attacker đã cố xoá dấu vết: log 1102 bị xoá, EDR bị vô hiệu hoá, log AV ghi nhận xử lý thất bại | recall × [gate] |
| [T1370.003](subtasks/T1370.003.md) | vm | Thêm yêu cầu thu đúng order of volatility, không chỉ thu đủ | Σ wᵢ·sᵢ |

### T1371 — Giảm thiểu các sự cố phòng thủ mạng tiềm tàng

**Source review:** Chuẩn nghiệp vụ. Benchmark chưa chuẩn.

| Subtask | Môi trường | Mô tả nghiệp vụ nguồn (tóm tắt) | Scorer nguồn |
|---|---|---|---|
| [T1371.001](subtasks/T1371.001.md) | file | Cho 1 danh sách IOC và danh mục tài sản, chọn IOC được phép chặn | F1 × [không chặn nhầm tài sản hợp lệ] |
| [T1371.002](subtasks/T1371.002.md) | file | Phải nêu chặn ở lớp nào: firewall, proxy, email gateway, WAF | F1 × [gate] |
| [T1371.003](subtasks/T1371.003.md) | soc | Cấy 1 domain CDN dùng chung và 1 IP của chính hệ thống giám sát vào đám IOC để bẫy việc chặn cả dải | F1 × Π[2 gate] |

### T1607 — Khôi phục thông tin từ các nguồn dữ liệu pháp y

**Source review:** Chuẩn nghiệp vụ, nhưng bài benchmark chưa chuẩn.

| Subtask | Môi trường | Mô tả nghiệp vụ nguồn (tóm tắt) | Scorer nguồn |
|---|---|---|---|
| [T1607.001](subtasks/T1607.001.md) | file | Cho log antivirus lịch sử, liệt kê các mã độc từng bị phát hiện nhưng xử lý thất bại | max(0, M′/M − N′/(N′+M′)) |
| [T1607.002](subtasks/T1607.002.md) | file | Thêm log hệ thống, phải dựng lại trình tự hành vi đã xảy ra trong quá khứ | Σ wᵢ·sᵢ |
| [T1607.003](subtasks/T1607.003.md) | soc | Cố ý xoá hẳn một khoảng log — nhãn cho khoảng đó là khong_du_du_kien, để đo model có phân biệt "không có" với "không quan sát được" hay không | Σ wᵢ·sᵢ × [nhận ra khoảng không quan sát được] |

### T1617 — Chuẩn bị các báo cáo phòng thủ mạng

**Source review:** Có nghiệp vụ nhưng không hẳn đúng như mô tả hiện tại. Tổng thể OK.

| Subtask | Môi trường | Mô tả nghiệp vụ nguồn (tóm tắt) | Scorer nguồn |
|---|---|---|---|
| [T1617.001](subtasks/T1617.001.md) | file | Cho 1 bản Technical Report, sinh bản Executive tương ứng — mọi con số ở bản Executive phải bằng đúng con số cùng khoá ở bản Technical | tỉ lệ con số khớp |
| [T1617.002](subtasks/T1617.002.md) | file | Thêm checklist mục bắt buộc của từng bản | Σ wᵢ·sᵢ |
| [T1617.003](subtasks/T1617.003.md) | file | Sinh **cả hai** bản executive.json và technical.json có khoá chung. Lỗi hay gặp thật: hai bản nói hai con số khác nhau về cùng một sự cố | Σ wᵢ·sᵢ |

### T0510 — Điều phối các chức năng ứng cứu sự cố

**Source review:** Nghiệp vụ Xử lý sự cố (IR) chuẩn. Chưa có bài benchmark.

| Subtask | Môi trường | Mô tả nghiệp vụ nguồn (tóm tắt) | Scorer nguồn |
|---|---|---|---|
| [T0510.001](subtasks/T0510.001.md) | file | Cho 1 sự cố mới tiếp nhận và ma trận severity, trả lời mức độ và tier xử lý | [severity] × [tier] |
| [T0510.002](subtasks/T0510.002.md) | file | Thêm danh mục log source, phải liệt kê artifact phải thu ngay vì sẽ bị ghi đè | Σ wᵢ·sᵢ |
| [T0510.003](subtasks/T0510.003.md) | soc | Ràng buộc kiểm bằng luật: phản hồi ≤ 30 phút với mức High, bắt đầu thu thập ≤ 10 phút sau khi xác nhận phạm vi | Σ wᵢ·sᵢ ; cap 0.5 nếu sai mốc SLA |

### T1109 — Xử lý các sự cố phòng thủ mạng

**Source review:** Tag `mon`, `ir` chuẩn — đúng nghiệp vụ: Giám sát đóng sự cố đã có hướng dẫn theo SLA, IR thực hiện Eradication & Recovery. Chưa có benchmark đo task này (tier none).

| Subtask | Môi trường | Mô tả nghiệp vụ nguồn (tóm tắt) | Scorer nguồn |
|---|---|---|---|
| [T1109.001](subtasks/T1109.001.md) | vm | Cho 1 máy ảo có M webshell và 1 backdoor cron, gỡ sạch cả hai loại mà không xoá file sạch | Π[3 điều kiện] |
| [T1109.002](subtasks/T1109.002.md) | vm | Thêm tài khoản attacker tự tạo — phải phát hiện qua log xác thực rồi xoá | Π[4 điều kiện] |
| [T1109.003](subtasks/T1109.003.md) | vm | M = 6 thành phần phải gỡ. reward = 1 chỉ khi **dịch vụ web vẫn phục vụ được** — điều kiện này phân biệt IR thật với "xoá cho sạch" | Π[4 điều kiện] |

### T1250 — Thực hiện phân loại ưu tiên sự cố phòng thủ mạng (triage)

**Source review:** OK — tag và mô tả nghiệp vụ chuẩn.

| Subtask | Môi trường | Mô tả nghiệp vụ nguồn (tóm tắt) | Scorer nguồn |
|---|---|---|---|
| [T1250.001](subtasks/T1250.001.md) | file | Cho 1 cảnh báo tại thời điểm vừa nhận, trả lời loại sự cố có khả năng xảy ra | [incident_type] |
| [T1250.002](subtasks/T1250.002.md) | file | Thêm ma trận, phải phân loại cả mức độ | Σ wᵢ·sᵢ |
| [T1250.003](subtasks/T1250.003.md) | soc | Chỉ cấp dữ kiện có tại t0, tuyệt đối không cấp kết luận về sau — đây là điểm phân biệt duy nhất với T1252 | Σ wᵢ·sᵢ |

### T1251 — Khuyến nghị chiến lược khắc phục sự cố

**Source review:** OK — tag và mô tả nghiệp vụ chuẩn.

| Subtask | Môi trường | Mô tả nghiệp vụ nguồn (tóm tắt) | Scorer nguồn |
|---|---|---|---|
| [T1251.001](subtasks/T1251.001.md) | file | Cho 8 bước khắc phục bị xáo trộn, sắp lại đúng thứ tự (gỡ webshell trước khi vá lỗ hổng) | Kendall tau |
| [T1251.002](subtasks/T1251.002.md) | file | Phải tự liệt kê tập bước, không cho sẵn | Σ wᵢ·sᵢ |
| [T1251.003](subtasks/T1251.003.md) | file | Kế hoạch thiếu một cửa hậu là kế hoạch hỏng, nên bỏ sót bị chặn trần chứ không trừ dần | Σ wᵢ·sᵢ ; cap 0.3 nếu sót bất kỳ backdoor nào |

### T1252 — Xác định phạm vi, mức độ khẩn cấp và tác động của các sự cố phòng thủ mạng

**Source review:** Chuẩn nghiệp vụ.

| Subtask | Môi trường | Mô tả nghiệp vụ nguồn (tóm tắt) | Scorer nguồn |
|---|---|---|---|
| [T1252.001](subtasks/T1252.001.md) | file | Cho log xác thực của 1 sự cố, liệt kê các máy bị ảnh hưởng | F2 |
| [T1252.002](subtasks/T1252.002.md) | file | Thêm telemetry, phải liệt kê cả tài khoản bị lạm dụng | Σ wᵢ·sᵢ |
| [T1252.003](subtasks/T1252.003.md) | soc | Trước khi chốt nhãn phải tự kiểm mỗi phần tử có suy ra được từ hiện vật đã cấp không | Σ wᵢ·sᵢ |

### T1257 — Khuyến nghị các chiến lược giảm thiểu và khắc phục cho các hệ thống của doanh nghiệp

**Source review:** OK — tag và mô tả nghiệp vụ chuẩn.

| Subtask | Môi trường | Mô tả nghiệp vụ nguồn (tóm tắt) | Scorer nguồn |
|---|---|---|---|
| [T1257.001](subtasks/T1257.001.md) | file | Cho danh mục log source và 1 kỹ thuật đã bị khai thác, chỉ ra nguồn log còn thiếu để phát hiện được | F1 |
| [T1257.002](subtasks/T1257.002.md) | file | Thêm kho rule, phải chỉ ra cả rule / use-case còn thiếu | Σ wᵢ·sᵢ |
| [T1257.003](subtasks/T1257.003.md) | file | Ba trục tách biệt: kiểm soát kỹ thuật · năng lực phát hiện · quy trình. Riêng trục nguồn log chấm cứng bằng so tập với HV-04 | macro-average F1 trên 3 trục |

### T1315 — Theo dõi các sự cố phòng thủ mạng từ khi phát hiện đến khi xử lý xong

**Source review:** OK — tag và mô tả nghiệp vụ chuẩn.

| Subtask | Môi trường | Mô tả nghiệp vụ nguồn (tóm tắt) | Scorer nguồn |
|---|---|---|---|
| [T1315.001](subtasks/T1315.001.md) | file | Cho K case đang mở và bảng cam kết SLA, liệt kê các case sắp trễ hạn | F1 |
| [T1315.002](subtasks/T1315.002.md) | file | Phải xếp cả thứ tự xử lý K = 15 case đang mở đồng thời | Σ wᵢ·sᵢ |
| [T1315.003](subtasks/T1315.003.md) | soc | Deadline và tập trễ hạn do verifier tự tính bằng luật từ severity + timestamp — không cần người gán nhãn | (0.6·ρ + 0.4·F1) × [SLA] |

### T1316 — Ghi nhận các sự cố phòng thủ mạng từ khi phát hiện đến khi xử lý xong

**Source review:** OK — tag và mô tả nghiệp vụ chuẩn.

| Subtask | Môi trường | Mô tả nghiệp vụ nguồn (tóm tắt) | Scorer nguồn |
|---|---|---|---|
| [T1316.001](subtasks/T1316.001.md) | file | Cho 1 hồ sơ case bị xoá M mục, liệt kê các mục còn thiếu | max(0, M′/M − N′/(N′+M′)) |
| [T1316.002](subtasks/T1316.002.md) | file | Phải phân biệt mục **bắt buộc** với mục **nên có** — chỉ mục bắt buộc mới chặn việc đóng case | Σ wᵢ·sᵢ |
| [T1316.003](subtasks/T1316.003.md) | soc | Nhãn sinh tự động: script lấy bản đầy đủ, xoá ngẫu nhiên M mục rồi ghi lại danh sách đã xoá — **bài tự sinh vô hạn mẫu, không tốn công gán nhãn** | Σ wᵢ·sᵢ − 0.1 × (số mục đòi thừa) |

### T1332 — Lập báo cáo kết quả điều tra sự cố

**Source review:** OK — tag và mô tả nghiệp vụ chuẩn.

| Subtask | Môi trường | Mô tả nghiệp vụ nguồn (tóm tắt) | Scorer nguồn |
|---|---|---|---|
| [T1332.001](subtasks/T1332.001.md) | file | Cho 1 gói bằng chứng đã che kết luận, trả lời nguyên nhân gốc | [root_cause] |
| [T1332.002](subtasks/T1332.002.md) | file | Phải dựng cả chuỗi tấn công từ điểm xâm nhập tới hành vi cuối | Σ wᵢ·sᵢ |
| [T1332.003](subtasks/T1332.003.md) | file | Mọi khẳng định kèm trích dẫn để verifier grep lại — đúng nguyên tắc "kết luận phải dựa trên bằng chứng kỹ thuật" | Σ wᵢ·sᵢ |
