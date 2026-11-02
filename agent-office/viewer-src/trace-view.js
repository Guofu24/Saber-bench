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
};
function describeTool(tool) { return descriptions[tool] || 'Thực thi công cụ trong ứng dụng lab.'; }
function httpOutcome(status) {
  if (status === 403) return 'Yêu cầu bị từ chối';
  if (status === 401) return 'Chưa xác thực thành công';
  if (status >= 500) return 'Dịch vụ báo lỗi';
  if (status >= 400) return 'Yêu cầu không thành công';
  if (status === 202) return 'Yêu cầu được chấp nhận';
  return 'Yêu cầu thành công';
}
module.exports = { actorTrace, describeTool, httpOutcome };
