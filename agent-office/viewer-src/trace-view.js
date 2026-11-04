// Evidence-based selection only: sharing a tick/target does not link two incidents.
function actorTrace(world, actorId) {
  if (!world.trace) return null;
  const own = world.trace.events.filter(e => e.actor_id === actorId);
  const ownIds = new Set(own.map(e => e.id));
  const cases = world.trace.cases.filter(c => c.evidence_ids.some(id => ownIds.has(id))
    || own.some(e => e.case_id === c.id) || c.responses.some(r => r.actor_id === actorId));
  const caseIds = new Set(cases.map(c => c.id));
  const evidence = new Set(cases.flatMap(c => c.evidence_ids));
  const events = world.trace.events.filter(e => ownIds.has(e.id) || evidence.has(e.id)
    || caseIds.has(e.case_id) || e.target_actor_id === actorId);
  return { own, events, cases };
}

const descriptions = {
  forensic_sources: 'Liệt kê log do operator nhập vào kho bằng chứng.',
  forensic_open: 'Mở phiên điều tra trên các bản log đã lưu và đối chiếu SHA-256.',
  forensic_status: 'Đọc tiến độ và phát hiện đã lưu của phiên điều tra.',
  forensic_query: 'Truy vấn log theo từ khóa, timeline, IP hoặc tiến trình; kết quả có ID và hash bản ghi.',
  forensic_record: 'Ghi nhận định của analyst kèm ID bằng chứng đã đọc. Trích dẫn hợp lệ chưa chứng minh nhận định đúng.',
  response_review: 'Rà soát thiếu sót về phạm vi, cô lập, loại bỏ, khôi phục và rủi ro còn lại; không tự đóng case.',
  forensic_finish: 'Lưu kết luận điều tra với trạng thái REVIEWED hoặc PARTIAL; không xác nhận hệ thống đã an toàn.',
  consult_skill: 'Tra cứu hướng dẫn skill đã ghim cho agent; không tự thực hiện thao tác trong hệ thống đích.',
  browse: 'Khám phá các đường dẫn trong ứng dụng lab.',
  login: 'Đăng nhập vào ứng dụng lab.',
  search: 'Tìm tài liệu trong ứng dụng.',
  read_document: 'Yêu cầu đọc tài liệu tại mục tiêu bên dưới.',
  write_document: 'Cập nhật tài liệu làm việc.',
  collect: 'Yêu cầu sao chép dữ liệu đã đọc vào kho nội bộ lab.',
  register_job: 'Đăng ký automation trong ứng dụng; không thực thi trên hệ điều hành.',
  disrupt: 'Yêu cầu gây gián đoạn có thời hạn cho dịch vụ lab.',
  share: 'Gửi thông tin vào kênh riêng của đội.',
  query_events: 'Truy vấn telemetry được cấp quyền.',
  open_case: 'Mở case dựa trên các event được dẫn chứng.',
  investigate: 'Dựng timeline từ bằng chứng của case.',
  contain: 'Hạn chế phiên của tài khoản được gắn với bằng chứng.',
  quarantine: 'Vô hiệu hóa job trong ứng dụng lab.',
  unquarantine: 'Khôi phục job đã cách ly trong case.',
  restore: 'Yêu cầu khôi phục dịch vụ lab.',
  release: 'Gỡ hạn chế tài khoản.',
  patch: 'Cập nhật kiểm soát truy cập của ứng dụng.',
  deploy_rule: 'Triển khai rule phát hiện trong lab.',
  notify: 'Gửi cảnh báo cho client.',
  verify_recovery: 'Kiểm tra trạng thái phục hồi của client.',
  close_case: 'Yêu cầu đóng case theo điều kiện của runtime.',
  list_samples: 'Liệt kê mẫu được operator đăng ký trong vault, định danh bằng SHA-256.',
  tool_status: 'Kiểm tra engine phân tích nào có sẵn trong môi trường thực thi.',
  analyze_sample: 'Đưa mẫu vào hàng đợi phân tích tĩnh. Xem receipt và report sau khi job hoàn tất.',
  analysis_status: 'Đọc trạng thái và kết quả của job phân tích đã gửi.',
  run_playbook: 'Chạy playbook gắn với case; kiểm bằng chứng và trạng thái dịch vụ sau phản ứng.',
  soar_status: 'Đối soát job SOAR cũ; không tự gửi lại hiệu ứng chưa rõ kết quả.',
  query_siem: 'Truy vấn event đã được index trong OpenSearch.',
  export_case: 'Xuất bằng chứng case sau khi đối chiếu hash với collector.',
  timeline: 'Sắp xếp bằng chứng đã xác minh theo thời gian.',
  hunt: 'Tìm dấu hiệu theo các trường của telemetry được cấp quyền.',
  network_hunt: 'Truy vấn các kết nối, địa chỉ, DNS và bằng chứng mạng được thu thập.',
  identity_hunt: 'Truy vấn sự kiện xác thực và tài khoản trong lab.',
  windows_work: 'Xếp tác vụ người dùng cố định vào queue của guest Windows.',
  windows_recon: 'Xếp tác vụ inventory giới hạn trong guest Windows của lab.',
  windows_failed_logon: 'Tạo thử nghiệm đăng nhập thất bại có giới hạn với tài khoản tổng hợp.',
  windows_job_status: 'Đọc receipt của tác vụ guest; queued chưa phải đã thực thi.',
  windows_collect_evidence: 'Yêu cầu guest thu thập bằng chứng hệ thống được phép.',
  windows_inventory: 'Yêu cầu inventory cố định trên guest đã cấu hình.',
  contain_domain_user: 'Yêu cầu khóa tài khoản thử nghiệm; chờ xác minh AD và lịch rollback.',
};
function describeTool(tool) { return descriptions[tool] || 'Thực thi công cụ được cấp quyền trong môi trường lab; xem bằng chứng bên dưới.'; }
function rangeEvidenceSummary(entry) {
  if ((entry.tool.startsWith('forensic_') || entry.tool === 'response_review') && entry.result?.analysis_only === true) {
    return 'Phân tích log nhập tại controller. Hash xác nhận bản ghi lưu giữ, không xác nhận nội dung log là thật hay phản ứng đã thành công. Không tạo tiến trình trên máy đích.';
  }
  if (entry.tool === 'consult_skill' && entry.result?.guidance_only === true) {
    return 'Tra cứu hướng dẫn tại controller. Xem status và topic trong kết quả; thao tác này không tạo process hay bằng chứng thực thi trên máy đích.';
  }
  return entry.evidence_complete
    ? 'Đã nhận và kiểm hash log khởi chạy/kết thúc cùng bằng chứng được dẫn chiếu.'
    : 'Bằng chứng chưa đầy đủ trong cửa sổ này; không suy ra thao tác thành công.';
}
function httpOutcome(status) {
  if (status === 403) return 'Yêu cầu bị từ chối';
  if (status === 401) return 'Chưa xác thực thành công';
  if (status >= 500) return 'Dịch vụ báo lỗi';
  if (status >= 400) return 'Yêu cầu không thành công';
  if (status === 202) return 'Đã nhận yêu cầu; đang chờ thực thi hoặc kết quả';
  return 'Yêu cầu thành công';
}
module.exports = { actorTrace, describeTool, httpOutcome, rangeEvidenceSummary };
