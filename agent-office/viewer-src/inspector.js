import { actorTrace, describeTool, httpOutcome } from './trace-view.js';

const $inspector = document.getElementById('inspector');
const $timeline = document.getElementById('traceTimeline');
let detailEventId = null, detailSignature = '';
let nativeRequest = null;
let nativePanelKey = '';

async function renderNative(world, actor, event) {
  nativeRequest?.abort();
  const request = nativeRequest = new AbortController();
  const panel = document.getElementById('nativeEvents'), hint = document.getElementById('nativeScope');
  if (world.execution_mode === 'range') {
    document.getElementById('inspectorScope').textContent = 'HOẠT ĐỘNG ĐÃ THỰC THI · SOC LAB';
    const e = actor.executor;
    hint.textContent = 'Job chạy tại executor riêng. Log đầy đủ và bằng chứng Sysmon/Zeek xem trong SOC; bên dưới là receipt gần nhất của agent.';
    panel.innerHTML = e ? `<div class="trace-case"><b>${esc(e.host || 'Chưa nhận receipt')}</b><p>PID ${e.pid ?? '—'} · exit ${e.exit_code ?? '—'}</p><p>Job ${esc(e.job_id || '—')}</p>${e.pending ? '<p>Đang chờ kết quả hoặc đối soát job; chưa xác nhận hiệu ứng.</p>' : ''}<ul>${e.artifacts.map(f => `<li><b>${esc(f.name)}</b> · ${f.bytes} bytes<pre style="white-space:pre-wrap;overflow-wrap:anywhere">SHA-256 ${esc(f.sha256)}</pre></li>`).join('')}</ul></div>` : '<p>Chưa nhận receipt thực thi.</p>';
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
      <p class="muted">HTTP thành công xác nhận yêu cầu đã xử lý; kết luận xâm nhập và hiệu quả phòng thủ cần bằng chứng bổ sung.</p>`;
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
