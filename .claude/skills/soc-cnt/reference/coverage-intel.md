# CNT · Độ phủ ATT&CK, use-case hunting và tình báo thành rule

## Độ phủ theo intrusion set và use-case hunting

Săn theo **giả thuyết**: từ một kỹ thuật tấn công mới trong MITRE ATT&CK, xây **use-case hunting** rồi truy vấn
event log xem hệ thống khách hàng có dấu vết tương tự không. Từ hiểu biết về một nhóm tấn công (họ dùng kỹ
thuật gì, tool gì, hạ tầng nào), xây **các bước lặp lại được** để nhận diện và truy vết đúng nhóm đó mỗi khi nó
xuất hiện. Đầu ra: bộ use-case hunting theo technique và kết quả kiểm chứng trên log thật.

**Một technique chỉ được coi là "đã phủ" khi đủ hai điều**
1. Có ít nhất một rule **đang bật** trong kho rule được map **đúng technique** đó (so đúng cấp: `T1059.001` khác
   `T1059`; rule cấp cha không tự động phủ sub-technique trừ khi mapping ghi vậy).
2. **Nguồn log** mà rule cần **đã on-board và đang khoẻ**. Rule có mà nguồn log thiếu/hỏng thì thực tế là **không
   phủ**.

**Rà độ phủ một intrusion set:** duyệt từng technique của nhóm, áp hai điều kiện trên, ra danh sách technique
chưa phủ — chỉ trong phạm vi intrusion set, không thêm technique ngoài.

**Xây use-case hunting**
1. Viết truy vấn **chạy được** bắt dấu vết của technique (hẹp như một rule phát hiện — `engines.md`).
2. **Kiểm nguồn log trước khi kết luận.** Nếu nguồn log cần cho technique **không tồn tại**, kết luận đúng là
   **"không đủ dữ liệu"** (`insufficient_data`) — **không phải** "không có dấu vết". Không quan sát được ≠ không
   xảy ra.
3. Ghi kết quả vào báo cáo TH/CA và cập nhật mapping trong kho rule.

```json
{"intrusion_set": "…", "uncovered": ["T1003.001", "T1021.002"],
 "hunt_query": {"engine": "regex", "pattern": "…", "ignore_case": true},
 "result": "insufficient_data", "missing_log_source": "Sysmon EID 10 trên nhóm máy chủ"}
```

## Chuyển tình báo thành chỉ dấu và rule

Chuyển thông tin chiến dịch, lỗ hổng và IOC từ Threat Intelligence thành **rule giám sát khả thi**, **bộ chỉ dấu
săn tìm** và **chữ ký YARA/Sigma**. Đầu ra là chỉ dấu tác nghiệp dạng **rule chạy được trên SIEM khách hàng**.

### Trích IOC từ báo cáo TI

Gom theo sáu loại: `ipv4`, `domain`, `url`, `sha256`, `email`, `cve`.

- **Giữ giá trị gốc, nguồn, thời điểm và vai trò** của mỗi observable. Refang `hxxp` → `http`, `[.]`/`(.)` → `.`,
  `[@]` → `@` để đối chiếu; không truy cập URL chỉ vì đã refang.
- **Chuẩn hoá theo loại:** hash/domain dùng chữ thường; URL chỉ hạ chữ scheme/host, giữ path/query và dấu `/`
  có ý nghĩa. Không hạ chữ email local-part mặc định. Quy tắc so sánh riêng do case yêu cầu áp dụng trên bản so sánh,
  không ghi đè bản gốc. [RFC 3986 §6.2.2.1](https://www.rfc-editor.org/rfc/rfc3986.html#section-6.2.2.1).
- **Observable chưa phải IOC độc hại:** cần ngữ cảnh và bằng chứng. IP private/domain nội bộ có thể là hạ tầng
  bị chiếm; IP công khai/CDN có thể là dịch vụ hợp lệ. Lọc theo phạm vi case và căn cứ, không chỉ theo lớp địa chỉ.
  Tên tệp/đoạn path không tự trở thành domain; CVE là tham chiếu lỗ hổng, chưa chứng minh đã khai thác.
- **Dedupe trong từng loại theo contract.** Chỉ xuất host/domain suy ra từ URL/email nếu case yêu cầu hoặc có
  quan sát độc lập; ghi quan hệ nguồn để không đếm thành hai bằng chứng độc lập.
- Loại hiếm (cve, email) quan trọng ngang loại phổ biến — đừng bỏ sót.

```json
{"ioc": {"ipv4": ["203.0.113.9"], "domain": ["upd-check.example-cdn.net"],
         "url": ["http://198.51.100.4/gate.php"], "sha256": ["…"], "email": ["billing@fake-invoice.net"],
         "cve": ["CVE-2023-4966"]}}
```

### Phân loại độ bền của chỉ dấu (Pyramid of Pain)

| Loại | Độ bền | Vì sao |
|---|---|---|
| hash | thấp nhất | biên dịch lại/thêm byte là đổi |
| IP, domain | thấp–trung bình | đổi hạ tầng tốn ít chi phí |
| TTP (hành vi, chuỗi kỹ thuật, cấu trúc C2) | **cao** | khó đổi; giá trị phát hiện lâu dài |

```json
{"durability": {"4b92eb38…": "hash đổi được", "upd-check.example-cdn.net": "domain đổi được",
                "beacon HTTPS 60s qua rundll32": "TTP khó đổi"}}
```

### Từ IOC tới rule chạy được

1. Rule đáng giá nhất bám **TTP bền** (hành vi trong báo cáo phân tích mã độc, chuỗi tiến trình, cơ chế
   persistence), không chỉ là danh sách hash/IP chép lại — chép bảng IOC thì máy làm được.
2. Kiểm nguồn log rule cần có trong danh mục log source (như phần độ phủ ở trên).
3. Viết và kiểm thử theo `engines.md`; ghi technique ATT&CK và phiên bản.

## Sai lầm thường gặp

- Coi rule tồn tại là đã phủ mà không kiểm nguồn log.
- Kết luận "không có dấu vết" khi thật ra thiếu nguồn log.
- Loại mọi IP private/domain nội bộ, hạ chữ cả URL hoặc bỏ dấu `/` làm mất phân biệt tài nguyên.
- Chỉ nộp bảng IOC mà không có rule hành vi.

Nguồn nghiệp vụ: NICE T1384, T1644 (catalog SABER).
