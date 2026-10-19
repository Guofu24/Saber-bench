# Hợp đồng benchmark subtask — cần implement

Tài liệu này là **đề xuất kiến trúc** để hiện thực hóa dữ liệu người dùng cung cấp; các trường có hậu tố `_source` là nguyên văn từ HTML.

## Mẫu `SubtaskSpecV1` (hợp đồng tương lai)

```json
{
  "id": "T1112.001",
  "nice_id": "T1112",
  "service": "MON",
  "environment": "file",
  "task_version": "1.0.0",
  "source_sha256": "<SHA256 of frozen HTML>",
  "inputs": [{"hv_id": "HV-01", "path": "inputs/alert.json", "sha256": "<checksum>", "visibility": "blue"}],
  "outputs": {"schema_ref": "schemas/T1112.001.output.schema.json"},
  "scoring": {"implementation": "grader:T1112.001@1", "source_formula": "[verdict]"},
  "private_truth_ref": "sealed://episode/<id>/truth",
  "tool_policy": {"default": "deny", "allow": ["read_fixture"]},
  "time_policy": {"observation_cutoff": "<UTC time>", "visibility_cutoff": "<UTC time>"},
  "timeouts": {"episode_seconds": 300, "tool_calls": 20},
  "invalidity": ["missing_required_evidence", "snapshot_contaminated"]
}
```

Trường minh họa `tool_calls=20`, `episode_seconds=300` **không được mặc nhiên dùng cho 175 task**; cần chọn theo từng task và dùng ngân sách so sánh công bằng.

## Thành phần bắt buộc

1. **Artifact Registry**: HV-01…HV-40 với version, source host/tenant, event UTC, ingest/visible UTC, sha256, role visibility, owner, sensitivity label và retention.
2. **Episode Builder**: đối với mỗi `T####.NNN`, build manifest public, private truth, fixture files, clean snapshot (`vm`), data source health (`soc`), checksum inventory.
3. **Runner**: cấp agent-visible inputs, gateway với quyền tối thiểu, audit mọi tool call, thu final JSON, terminate theo budget.
4. **Sealed Grader**: evaluator dùng nhãn ẩn; function registry theo field type và hard gates; không thực thi string công thức nguồn bằng `eval`.
5. **Result**: score components, hard-gate outcomes, validity, runtime/cost, evidence references, reproducibility manifest, scorer version.

## Output DTO

Output mỗi subtask có schema độc lập, không gom mọi bài thành JSON chung tùy ý. Mọi DTO đều có `episode_id`, `subtask_id`, `answer`, `evidence_refs` (nếu task yêu cầu), `abstain_reason` và `submitted_at`. Metadata không được chứa hidden truth hoặc các trường giải mã seed. Không ép `evidence_refs` lên bài file mà nguồn không yêu cầu: có thể coi là trace phụ, không thay công thức gốc.

Các trường source `items` như `` `verdict` · enum · 1.0 `` là **chỉ dẫn chuyển đổi** chứ chưa phải hợp đồng kiểu thực thi. Agent phải trả giá trị enum đã chốt trong `schemas/`.

## Các trạng thái episode

`CREATED → PREPARED → RUNNING → SUBMITTED → GRADED`, hoặc `INVALID`/`FAILED` với failure reason. Kịch bản tấn công không thành công, thiếu bắt buộc telemetry hoặc snapshot bị nhiễm trước run → `INVALID`, không tính FN. Mỗi lần test phải restore/reseed hoặc reset hoàn toàn case state.

## Quy tắc dữ liệu

- Source: raw event/artifact không bị biên tập nhãn; manifest user-facing không lộ nhãn, mục tiêu, kế hoạch attack đã ẩn, seed.
- Có cùng host/user/campaign ở nhiều split thì cần nhóm leakage kiểm tra; hidden GT ngoài runtime/credential của agent.
- SOC stateful: phân biệt event-time với ingest-time và visible-time; backend chặn future events, kể cả trong pagination và cache.
- VM: log full action, đo file hash trước/sau, service health và rollback; mọi thao tác có khả năng phá hủy phải duyệt cụ thể.

## Ranh giới dữ liệu khách hàng

Dữ liệu SOAR/SIEM/TH/IR có thể chứa danh tính, dữ liệu cá nhân, token, secrets, IP nội bộ và chi tiết nhạy cảm. Bắt buộc có quy trình cấp phép, de-identification, secret scanning, separation khách hàng, export audit và retention. Không đưa raw khách hàng lên public benchmark hoặc dịch vụ LLM bên ngoài nếu chưa được phê duyệt.
