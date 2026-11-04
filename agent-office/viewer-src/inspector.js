import { actorTrace, describeTool, httpOutcome, rangeEvidenceSummary } from './trace-view.js';

const $inspector = document.getElementById('inspector');
const $timeline = document.getElementById('traceTimeline');
function forensicDetail(data) {
  if (!data) return '';
  const query = data.query?.args;
  const gaps = { scope: 'Phạm vi ảnh hưởng', containment: 'Bằng chứng cô lập', eradication: 'Bằng chứng loại bỏ', recovery: 'Bằng chứng khôi phục', no_queries: 'Chưa truy vấn', source_coverage_or_time_uncertainty: 'Dữ liệu thiếu hoặc thời gian chưa rõ' };
  const evidence = Array.isArray(data.evidence) ? data.evidence : [];
  const samples = evidence.filter(e => e && e.fields).map(e => `<article class="trace-case"><b>Bản ghi #${esc(e.id)} · ${esc(e.fields.ts || 'Chưa rõ UTC')}</b><p>${esc([e.fields.host, e.fields.image, e.fields.ip, e.fields.status && `status ${e.fields.status}`].filter(Boolean).join(' · '))}</p><pre style="white-space:pre-wrap;overflow-wrap:anywhere">${esc(e.preview || '')}</pre><small>Nguồn ${esc(e.source_id)} · dòng ${esc(e.record)}</small><details><summary>SHA-256 bản ghi</summary><code style="overflow-wrap:anywhere">${esc(e.sha256)}</code></details></article>`).join('');
  const review = Array.isArray(data.gaps) ? `<b>Thiếu sót cần xử lý</b>${data.gaps.length ? `<ul>${data.gaps.map(g => `<li>${esc(gaps[g] || g)}</li>`).join('')}</ul>` : '<p>Đủ nhóm thông tin để rà hồ sơ; chưa kiểm chứng nội dung nhận định.</p>'}<p>Rủi ro còn lại: ${esc(data.residual_risk || '—')}</p>` : '';
  const finding = data.finding ? `<b>Nhận định · ${esc(data.finding.category)}</b><p>${esc(data.finding.text)}</p><p>ID được dẫn: ${esc((Array.isArray(data.finding.evidence_ids) ? data.finding.evidence_ids : []).join(', '))}</p>` : '';
  return `<section class="trace-case forensic-detail"><b>Điều tra log đã nhập</b><p>Phiên ${esc(data.session_id || data.id || '—')} · ${esc(data.state || '—')} · ${esc(data.step_count ?? 0)}/${esc(data.step_limit ?? 200)} bước</p>${query && data.query.tool === 'forensic_query' ? `<p><b>Truy vấn ${esc(query.mode || 'search')}</b> · ${esc(query.text || 'Theo bộ lọc')}</p>` : ''}${samples}${finding}${review}${data.summary ? `<p>${esc(data.summary)}</p>` : ''}<p class="muted">REVIEWED là hoàn tất rà soát hồ sơ. Hash hợp lệ không chứng minh xâm nhập hay phòng thủ thành công. Tối đa 3 bản ghi mẫu, 20 ID.</p><details><summary>Chi tiết truy vấn và bằng chứng</summary><pre style="white-space:pre-wrap;overflow-wrap:anywhere">${esc(JSON.stringify(data, null, 2))}</pre></details></section>`;
}
let detailEventId = null, detailSignature = '';
let nativeRequest = null;
let nativePanelKey = '';

function rangeJobProgress(result) {
  const job = result?.analysis_job || result?.soar_job;
  if (!job) return '';
  const labels = { QUEUED: 'Chờ thực thi', DISPATCHING: 'Đang gửi tác vụ', RUNNING: 'Đang chạy',
    VERIFYING: 'Đang đối chiếu bằng chứng', SUCCEEDED: 'Đã hoàn tất', FAILED: 'Thất bại',
    INDETERMINATE: 'Chưa xác định — cần kiểm tra receipt', UNAVAILABLE: 'Công cụ chưa sẵn sàng' };
  const operation = job.request?.engine || job.request?.playbook || '';
  const note = job.state === 'SUCCEEDED'
    ? (result.soar_job ? 'Phản ứng đã được đối chiếu với log và trạng thái dịch vụ.' : 'Phân tích đã chạy; kết quả không tự xác nhận mẫu là mã độc.')
    : 'HTTP của worker không xác nhận job bên dưới đã thành công.';
  return `<p><b>${esc(operation)} · ${esc(labels[job.state] || job.state)}</b></p><p class="muted">${note}</p>`;
}

async function renderNative(world, actor, event) {
  nativeRequest?.abort();
  const request = nativeRequest = new AbortController();
  const panel = document.getElementById('nativeEvents'), hint = document.getElementById('nativeScope');
  document.getElementById('nativeHistoryLabel').textContent = world.execution_mode === 'range'
    ? 'Lịch sử riêng của agent (tối đa 12 job)' : 'Lịch sử riêng của agent (tối đa 100 bản ghi)';
  if (world.execution_mode === 'range') {
    document.getElementById('inspectorScope').textContent = 'HOẠT ĐỘNG ĐÃ THỰC THI · SOC LAB';
    const e = actor.executor;
    const key = `range/${world.world_id}/${actor.id}/${document.getElementById('nativeAll').checked}`;
    const same = key === nativePanelKey;
    const expanded = new Set(same ? [...panel.querySelectorAll('details[open]')].map(n => n.dataset.job) : []);
    const scroll = same ? panel.scrollTop : 0, screenOpen = same && panel.querySelector('.range-screen')?.open;
    nativePanelKey = key;
    hint.textContent = '12 job gần nhất của agent; mở từng job để xem kết quả và bằng chứng. Hash được controller đối chiếu trước khi ẩn thông tin nhạy cảm. Ảnh là lần chụp trình duyệt gần nhất, không phải luồng desktop trực tiếp.';
    if (!same) panel.innerHTML = e ? `<div class="trace-case"><b>${esc(e.host || 'Chưa nhận receipt')}</b>${(actor.last_tool === 'consult_skill' || actor.last_tool?.startsWith('forensic_') || actor.last_tool === 'response_review') ? `<p>${esc(describeTool(actor.last_tool))}</p>` : `<p>PID ${e.pid ?? '—'} · exit ${e.exit_code ?? '—'}</p>`}<p>Job ${esc(e.job_id || '—')}</p>${e.pending ? '<p>Đang chờ kết quả hoặc đối soát job; chưa xác nhận hiệu ứng.</p>' : ''}<ul>${e.artifacts.map(f => `<li><b>${esc(f.name)}</b> · ${f.bytes} bytes<pre style="white-space:pre-wrap;overflow-wrap:anywhere">SHA-256 ${esc(f.sha256)}</pre></li>`).join('')}</ul></div>` : '<p>Chưa nhận receipt thực thi.</p>';
    try {
      const query = new URLSearchParams({ world: world.world_id, actor: actor.id });
      const response = await fetch(`/range-events?${query}`, { signal: request.signal, cache: 'no-store' });
      if (!response.ok) throw new Error('unavailable');
      const page = await response.json();
      if (nativeRequest !== request || selected?.worldActor?.id !== actor.id || currentWorld()?.world_id !== world.world_id) return;
      const all = document.getElementById('nativeAll').checked;
      const rows = all ? page.entries : page.entries.filter(e => e.event_id === event?.id);
      const screen = page.screen ? `<details class="trace-case range-screen"${screenOpen ? ' open' : ''}><summary>Ảnh trình duyệt thật · tick ${page.screen.tick}</summary><p>Job ${esc(page.screen.job_id)}</p><img alt="Ảnh trình duyệt của ${esc(actor.id)} tại tick ${page.screen.tick}" style="max-width:100%;height:auto" src="data:image/png;base64,${page.screen.png}"><p style="overflow-wrap:anywhere">SHA-256 ${esc(page.screen.sha256)}</p></details>` : '<p class="muted">Chưa có ảnh trình duyệt được xác minh cho agent này. Tác vụ dòng lệnh xem qua bằng chứng bên dưới.</p>';
      const json = value => `<pre style="white-space:pre-wrap;overflow-wrap:anywhere">${esc(JSON.stringify(value, null, 2))}</pre>`;
      panel.innerHTML = screen + (rows.length ? [...rows].reverse().map(entry => `<details class="trace-case range-job" data-job="${entry.job_id}"${expanded.has(entry.job_id) || !all ? ' open' : ''}><summary><b>${esc(entry.tool)}</b> · tick ${entry.tick} · ${esc(entry.source)}</summary><p>Job ${esc(entry.job_id)}</p>${rangeJobProgress(entry.result)}${entry.result.forensics ? forensicDetail(entry.result.forensics) : json(entry.result)}<p>${esc(rangeEvidenceSummary(entry))}</p>${entry.evidence.map(p => `<details><summary>${esc(p.event.kind)} · ${esc(p.event.host)} · ${esc(p.event.ts)}</summary>${json(p.event.data)}<p>${esc(p.event.sensor)} · ${esc(p.event.id)}</p><p style="overflow-wrap:anywhere">Hash bản gốc ${esc(p.sha256)} · ${p.hash_verified ? 'đã đối chiếu' : 'chưa đối chiếu'}</p></details>`).join('')}<p>Artifacts</p>${json(entry.artifacts)}</details>`).join('') : '<p class="muted">Thao tác chưa có trong cửa sổ bằng chứng. Bật lịch sử riêng để xem các job còn lưu trong cửa sổ.</p>');
      panel.scrollTop = scroll;
    } catch (error) {
      if (error.name !== 'AbortError' && nativeRequest === request) hint.textContent += ' Chưa đọc được export chi tiết; đang hiển thị receipt gần nhất.';
    }
    return;
  }
  document.getElementById('inspectorScope').textContent = world.execution_mode === 'native'
    ? 'HOẠT ĐỘNG ĐÃ THỰC THI · NATIVE WORKLOAD + APPLICATION LAB'
    : `HOẠT ĐỘNG ĐÃ THỰC THI · ${executionName(world).toUpperCase()}`;
  if (world.execution_mode !== 'native') {
    hint.textContent = world.execution_mode === 'application'
      ? 'World này chạy Application lab, chưa bật native execution. Chọn đúng world native để xem log process/file/DNS/network.'
      : 'Snapshot hoặc backend viewer cũ chưa cung cấp chế độ thực thi. Chưa thể kết luận world có log native hay không. Khởi động lại viewer bằng code mới với đúng thư mục world.';
    panel.replaceChildren(); return;
  }
  hint.textContent = 'saber-native-v1 · đo process và I/O của workload thật; chưa giám sát toàn hệ điều hành. DNS dùng máy chủ nội bộ, kết nối dùng loopback.';
  const all = document.getElementById('nativeAll').checked;
  const key = `${world.world_id}/${actor.id}/${all ? 'all' : event?.id}`;
  const same = key === nativePanelKey;
  const expanded = new Set(same ? [...panel.querySelectorAll('details[open]')].map(e => e.dataset.nativeId) : []);
  const scroll = same ? panel.scrollTop : 0;
  nativePanelKey = key;
  if (!same) panel.innerHTML = '<p class="muted">Đang đọc log riêng của agent…</p>';
  try {
    const query = new URLSearchParams({ world: world.world_id, actor: actor.id });
    const response = await fetch(`/native-events?${query}`, { signal: request.signal, cache: 'no-store' });
    if (!response.ok) throw new Error('unavailable');
    const page = await response.json();
    if (nativeRequest !== request || selected?.worldActor?.id !== actor.id || currentWorld()?.world_id !== world.world_id) return;
    const rows = all ? page.events : page.events.filter(e => e.event_id === event?.id);
    panel.innerHTML = rows.length ? `<p class="muted">${rows.length} bản ghi · cửa sổ riêng ${page.events.length}/${page.limit}. Lịch sử còn lưu trong SQLite xem bằng lệnh native-logs.</p>` + [...rows].reverse().map(e =>
      `<details class="trace-case native-row" data-native-id="${e.id}"${expanded.has(String(e.id)) ? ' open' : ''}><summary><b>${esc(e.kind)}</b> · PID ${e.pid} · #${e.id}</summary><p>${esc(e.ts)} · tick ${e.tick} · sự kiện ứng dụng ${e.event_id == null ? 'chưa xác nhận' : `#${e.event_id}`}</p><pre style="white-space:pre-wrap;overflow-wrap:anywhere">${esc(JSON.stringify(e.data, null, 2))}</pre><small>capture ${esc(e.capture_id)}</small></details>`
    ).join('') : '<p class="muted">Chưa có bản ghi tương ứng trong cửa sổ này. Bật lịch sử riêng để xem các thao tác khác.</p>';
    panel.scrollTop = scroll;
  } catch (error) {
    if (error.name === 'AbortError' || nativeRequest !== request) return;
    panel.innerHTML = '<p class="muted">Chưa đọc được log native. Dùng viewer mới với watch --world hoặc watch --bundle; kiểm tra agent đã chạy thao tác hay chưa.</p>';
  }
}

function selectAgent(agent) {
  selected = agent && selected !== agent ? agent : null;
  detailEventId = null; detailSignature = '';
  renderActorDetail();
  if (selected?.worldActor) document.getElementById('closeInspector').focus({ preventScroll: true });
}

function closeInspector() {
  const card = selected?.card;
  selected = null; detailSignature = ''; renderActorDetail();
  card?.focus({ preventScroll: true });
}

function renderActorDetail() {
  const world = currentWorld(), actor = selected?.worldActor;
  if (!world || !actor) { nativeRequest?.abort(); $inspector.hidden = true; return; }
  $inspector.hidden = false;
  document.getElementById('inspectorHealth').textContent = worldHealth(world) === 'stopped'
    ? 'World đã dừng · xem lại dữ liệu' : worldHealth(world) === 'stale'
      ? 'Mất cập nhật · dữ liệu cuối đã nhận' : 'Đang nhận dữ liệu';
  const scope = document.getElementById('traceRelated').checked;
  const signature = JSON.stringify([world.world_id, world.run_id, world.updated_at, actor.id, detailEventId, scope, document.getElementById('nativeAll').checked]);
  if (signature === detailSignature) return;
  detailSignature = signature;
  const focusedEvent = $inspector.contains(document.activeElement)
    ? document.activeElement.closest('[data-event-id]')?.dataset.eventId : null;
  $inspector.style.setProperty('--agent-color', teamColors[actor.team]);
  document.getElementById('inspectorTitle').textContent = actor.id;
  document.getElementById('inspectorRole').textContent = `${teamNames[actor.team]} · ${actor.role} · ${actorStatus(actor)}`;
  const trace = actorTrace(world, actor.id);
  const $window = document.getElementById('traceWindow');
  const $event = document.getElementById('traceEvent');
  const $cases = document.getElementById('traceCases');
  if (!trace) {
    renderNative(world, actor, null);
    $window.textContent = 'Snapshot cũ chưa có lịch sử thao tác. Chạy/resume world bằng code mới để xuất lịch sử.';
    $timeline.replaceChildren(); $event.replaceChildren(); $cases.replaceChildren(); return;
  }
  const all = world.trace.events;
  $window.textContent = `${all.length}/${world.trace.limit} sự kiện gần nhất của toàn world${all.length ? ` · tick ${all[0].tick}–${all[all.length - 1].tick}` : ''}. ${trace.own.length} thao tác của agent. Tối đa 12 case và 8 phản ứng/case; đây là cửa sổ dữ liệu, không phải toàn bộ lịch sử.`;
  const events = scope ? trace.events : trace.own;
  const event = detailEventId == null ? trace.own[trace.own.length - 1] : all.find(e => e.id === detailEventId);
  renderNative(world, actor, event);
  const scroll = $timeline.scrollTop;
  $timeline.innerHTML = events.length ? [...events].reverse().map(e => {
    const who = world.actors.find(a => a.id === e.actor_id);
    return `<button class="trace-row${event?.id === e.id ? ' chosen' : ''}" data-event-id="${e.id}" aria-pressed="${event?.id === e.id}" style="--event-color:${teamColors[who?.team] || '#8993c2'}"><span class="trace-mark"></span><span><small>Tick ${e.tick} · #${e.id} · ${esc(e.actor_id)}</small><b>${esc(e.tool)}</b><span>${esc(e.target || 'Không ghi nhận mục tiêu')}</span></span><span class="http ${e.status >= 400 ? 'http-error' : ''}">${e.status}</span></button>`;
  }).join('') : '<p class="muted">Chưa có thao tác phù hợp trong cửa sổ dữ liệu này.</p>';
  $timeline.scrollTop = scroll;
  if (event) {
    const source = event.source === 'unknown' ? 'Chưa ghi nhận nguồn quyết định' : event.source;
    $event.innerHTML = `<div class="trace-event-heading">Sự kiện #${event.id} · tick ${event.tick} · ${esc(source)}</div>
      <div class="trace-flow"><div><small>Agent</small><b>${esc(event.actor_id)}</b></div><span>→</span><div><small>Thao tác</small><code>${esc(event.tool)}</code></div><span>→</span><div><small>Mục tiêu</small><b>${esc(event.target || '—')}</b></div></div>
      <p>${esc(describeTool(event.tool))}</p><div class="trace-result ${event.status >= 400 ? 'http-error' : ''}">HTTP ${event.status} · ${esc(httpOutcome(event.status))}</div>
      <p class="muted">HTTP thành công xác nhận yêu cầu đã xử lý; kết luận xâm nhập và hiệu quả phòng thủ cần bằng chứng bổ sung.</p>${forensicDetail(event.forensics)}`;
  } else {
    $event.innerHTML = `<p class="muted">${detailEventId == null ? 'Chọn một thao tác để xem agent → công cụ → mục tiêu → kết quả.' : `Sự kiện #${detailEventId} đã ra khỏi cửa sổ dữ liệu. Chọn một sự kiện khác hoặc bấm Mới nhất.`}</p>`;
  }
  $cases.innerHTML = trace.cases.length ? trace.cases.map(c => {
    const responses = c.responses.map(r => `<li><small>Tick ${r.tick} · ${esc(r.actor_id)}</small><div><code>${esc(r.tool)}</code> → ${esc(r.target || '—')}</div><span class="${r.verified ? 'run' : 'muted'}">${r.verified ? 'Thay đổi đã được xác minh lúc thực thi' : 'Chưa xác minh được thay đổi mới'}</span></li>`).join('');
    const evidence = c.evidence_ids.map(id => `<button class="evidence-link" data-event-id="${id}">#${id}</button>`).join(' ');
    return `<article class="trace-case"><b>${esc(c.id)}</b><span class="case-state">${esc(c.status)}</span><p>Bằng chứng trong cửa sổ: ${evidence || 'không còn'} <small>(${c.evidence_ids.length}/${c.evidence_count})</small></p><ul>${responses || '<li class="muted">Chưa ghi nhận phản ứng trong dữ liệu case.</li>'}</ul></article>`;
  }).join('') : '<p class="muted">Chưa thấy case liên kết bằng chứng hoặc phản ứng của agent trong cửa sổ dữ liệu.</p>';
  if (focusedEvent) $inspector.querySelector(`[data-event-id="${focusedEvent}"]`)?.focus({ preventScroll: true });
}

$inspector.addEventListener('click', event => {
  const row = event.target.closest('[data-event-id]');
  if (!row) return;
  detailEventId = Number(row.dataset.eventId); renderActorDetail();
});
document.getElementById('closeInspector').addEventListener('click', closeInspector);
document.getElementById('traceLatest').addEventListener('click', () => { detailEventId = null; renderActorDetail(); });
document.getElementById('traceRelated').addEventListener('change', () => renderActorDetail());
document.getElementById('nativeAll').addEventListener('change', () => renderActorDetail());
document.addEventListener('keydown', event => {
  if (event.key === 'Escape' && !$inspector.hidden) closeInspector();
});
