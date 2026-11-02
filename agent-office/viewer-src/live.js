
// ================= live office (driven by agent-office events) =================
const SLOTS = [];
[[-7.0, -7.3], [-4.3, -7.3], [-7.0, -4.7], [-4.3, -4.7]].forEach(([x, z]) => SLOTS.push({ x, z, w: 1.5, sideX: -1.7, hub: [-2.4, 0.6] }));
for (const z of [-7.8, -5.8, -3.8, -1.8]) for (const x of [2.7, 4.5, 6.3, 8.05]) SLOTS.push({ x, z, w: 1.25, sideX: 1.15, hub: [0.9, 3.0] });
const FLOOR = []; for (const z of [3.4, 5.0, 6.6]) for (const x of [3.2, 4.6, 6.0, 7.4]) FLOOR.push({ x, z, used: null });
const PALETTE = ['#ff7eb6', '#4fd8ff', '#ffd36b', '#6bf29b', '#b892ff', '#ff9f5a', '#59d1c8', '#f2f28a'];
const IDLE_BREAK_MS = 20000;
const agents = [], byId = new Map();
const totals = { calls: 0, tools: 0, tokens: 0, handoffs: 0 };
let selected = null, hovered = null;

label('Phòng điều phối', 'zone', scene, 0.2, -5.4, -2.0);
label('Khu làm việc', 'zone', scene, 0.2, 5.3, 0.9);
label('Trạm Sức Khỏe', 'zone', scene, 0.2, -6.2, 7.6);
label('Lõi LLM', 'zone gold', scene, 2.35, CORE.x, CORE.z);
const waitL = label('Đang chờ world hoặc sự kiện agent…', 'tool say', scene, 2.9, CORE.x, CORE.z);

const boss = makeRobot('#ffd36b', { suit: true });
boss.position.set(2.0, 0, 3.6); boss.rotation.y = Math.atan2(2.0 - CORE.x, 3.6 - CORE.z);
scene.add(boss); boss.traverse(o => { if (o.isMesh) o.castShadow = true; });
const bossName = label('Sếp', 'nm', boss, 2.05); bossName.element.style.setProperty('--c', '#ffd36b');
const bossSay = label('', 'tool say', boss, 2.45); bossSay.visible = false;

const selRing = new THREE.Mesh(new THREE.RingGeometry(0.42, 0.5, 48), new THREE.MeshBasicMaterial({ color: '#fff', transparent: true, depthWrite: false }));
selRing.rotation.x = -Math.PI / 2; selRing.visible = false; scene.add(selRing);

function goTo(a, pts) {
  return new Promise(res => { a.mode = 'walk'; a.path = pts.map(([x, z]) => ({ x, z })); a.arrive = res; });
}
const headPos = a => () => a.robot.localToWorld(new THREE.Vector3(0, 1.5, 0));
const SOFA = [[-6.9, 3.25, Math.PI], [-6.1, 3.25, Math.PI], [-5.3, 3.25, Math.PI], [-8.0, 4.6, -Math.PI / 2]].map(([x, z, r]) => ({ x, z, r, used: null }));
const sofaFront = s => (s.r === Math.PI ? [s.x, 4.05] : [-7.1, s.z]);

function createAgent(ev) {
  const color = ev.color || PALETTE[agents.length % PALETTE.length];
  const a = { id: ev.id, name: ev.name, role: ev.role || '', color, activity: 'idle', mode: 'stand', path: [], faceTo: 0, where: 'spawn',
    calls: 0, tools: 0, tokens: 0, lastActive: performance.now(), status: 'Vừa vào văn phòng', task: '' };
  const slot = SLOTS.find(s => !s.used);
  if (slot) {
    slot.used = a; a.slot = slot;
    a.desk = slot.desk || (slot.desk = makeDesk(slot.x, slot.z, slot.w)); a.desk.g.visible = true;
    a.desk.g.traverse(o => { o.userData.agent = a; });
    a.seat = { x: slot.x, z: slot.z + 0.78 }; a.behind = { x: slot.x, z: slot.z + 1.32 }; a.side = { x: slot.sideX, z: slot.z + 1.32 };
  } else {
    const f = FLOOR.find(s => !s.used) || FLOOR[agents.length % FLOOR.length]; f.used = a; a.floor = f;
    a.side = { x: f.x, z: f.z };
  }
  const robot = makeRobot(color); a.robot = robot;
  const d = new THREE.Vector2(a.side.x - CORE.x, a.side.z - CORE.z).normalize();
  robot.position.set(CORE.x + d.x * 2.1, 0, CORE.z + d.y * 2.1);
  robot.rotation.y = Math.atan2(-d.x, -d.y);
  scene.add(robot); robot.traverse(o => { if (o.isMesh) { o.castShadow = true; o.receiveShadow = true; } o.userData.agent = a; });
  a.nameL = label(esc(a.name), 'nm', robot, 1.9); a.nameL.element.style.setProperty('--c', color);
  a.toolL = label('', 'tool', robot, 2.3); a.toolL.visible = false;
  agents.push(a); byId.set(a.id, a);
  addCard(a);
  waitL.visible = false;
  brain(a, !!ev.replay);
  return a;
}

async function brain(a, fast) {
  if (a.seat) {
    if (fast) { a.robot.position.set(a.seat.x, 0, a.seat.z); a.robot.rotation.y = 0; }
    else { flare = 1; pulse(); burst(orbPos, headPos(a), a.color, 6); await goTo(a, [[a.side.x, a.side.z], [a.behind.x, a.behind.z], [a.seat.x, a.seat.z]]); }
    a.faceTo = 0; a.where = 'desk';
  } else {
    if (fast) a.robot.position.set(a.side.x, 0, a.side.z); else await goTo(a, [[a.side.x, a.side.z]]);
    a.faceTo = Math.atan2(-(CORE.x - a.side.x), -(CORE.z - a.side.z)); a.where = 'floor';
  }
  while (!a.removed) {
    const now = performance.now();
    if (a.activity !== 'idle' && now - a.lastActive > 120000) { a.activity = 'idle'; hideTool(a); a.status = 'Không có hoạt động'; }
    if (a.activity !== 'idle') {
      if (a.where === 'lounge') await returnFromLounge(a);
      if (a.where === 'desk') { a.mode = 'type'; a.desk.on = true; } else if (a.where === 'floor') a.mode = 'stand';
    } else if (a.where === 'desk') {
      a.mode = 'sit'; a.desk.on = false;
      if (!a.worldActor && now - a.lastActive > IDLE_BREAK_MS && Math.random() < 0.015 && SOFA.some(s => !s.used)) await goLounge(a);
    } else if (a.where === 'floor') a.mode = 'stand';
    await wait(150);
  }
}
async function goLounge(a) {
  const s = SOFA.find(x => !x.used); if (!s) return; s.used = a; a.sofa = s;
  a.where = 'walking'; a.desk.on = false; a.status = 'Nghỉ ở Trạm Sức Khỏe ☕';
  await goTo(a, [[a.behind.x, a.behind.z], [a.side.x, a.side.z], a.slot.hub, sofaFront(s), [s.x, s.z]]);
  a.faceTo = s.r; a.mode = 'lounge'; a.where = 'lounge';
}
async function returnFromLounge(a) {
  const s = a.sofa; a.where = 'walking';
  await goTo(a, [sofaFront(s), a.slot.hub, [a.side.x, a.side.z], [a.behind.x, a.behind.z], [a.seat.x, a.seat.z]]);
  s.used = null; a.sofa = null; a.faceTo = 0; a.where = 'desk';
}

function showTool(a, txt) { a.toolL.element.textContent = txt; a.toolL.visible = true; clearTimeout(a.hideT); }
function hideTool(a) { a.toolL.visible = false; }
function bossSays(t, ms = 4000) { bossSay.element.textContent = t.length > 40 ? t.slice(0, 39) + '…' : t; bossSay.visible = true; clearTimeout(bossSays.t); bossSays.t = setTimeout(() => (bossSay.visible = false), ms); }

// ================= events =================
function onEvent(ev) {
  if (ev.type === 'world_snapshot') { receiveWorld(ev); return; }
  if (currentWorld()) return; // world roster/counters are authoritative, separate from proxy inference.
  const a = ev.id ? byId.get(ev.id) : null, fast = !!ev.replay, now = performance.now();
  switch (ev.type) {
    case 'agent':
      if (a) { a.name = ev.name || a.name; a.role = ev.role || a.role; a.nameL.element.textContent = a.name; a.card && (a.card.querySelector('b').textContent = a.name, a.card.querySelector('.rl').textContent = a.role); }
      else { const n = createAgent(ev); if (!fast) sys(`<b style="color:${n.color}">${esc(n.name)}</b> vừa vào văn phòng${n.role ? ' · ' + esc(n.role) : ''}`); }
      break;
    case 'task':
      if (!a) return; a.task = ev.title; a.status = 'Nhận việc: ' + ev.title; a.lastActive = now;
      log(a, '📥 ' + esc(ev.title), 'k-task');
      break;
    case 'llm_start':
      if (!a) return; a.activity = 'think'; a.lastActive = now; a.calls++; totals.calls++;
      a.status = 'Đang suy nghĩ' + (ev.model ? ' · ' + ev.model : '');
      showTool(a, '💭 ' + (ev.model || 'thinking…'));
      if (!fast) { burst(headPos(a), orbPos, a.color, 3); flare = Math.max(flare, 0.45); }
      break;
    case 'tool':
      if (!a) return; a.tools++; totals.tools++; a.activity = 'tool'; a.lastActive = now;
      showTool(a, '🔧 ' + ev.name); a.status = 'Gọi tool: ' + ev.name;
      break;
    case 'llm_end': {
      if (!a) return; const tk = (ev.usage ? ev.usage.in + ev.usage.out : 0); a.tokens += tk; totals.tokens += tk; a.lastActive = now;
      if (!fast) burst(orbPos, headPos(a), '#ffd36b', 3);
      if (ev.tools && ev.tools.length) {
        a.activity = 'tool'; const names = ev.tools.map(t => t.name);
        showTool(a, '🔧 ' + names.join(' · ')); a.status = 'Chạy tool: ' + names.join(', ');
        log(a, ev.tools.map(t => `<code>${esc(t.name)}</code> <small>${esc(t.args || '')}</small>`).join('<br>'), 'k-tool');
      } else {
        a.activity = 'idle'; a.status = 'Xong · ' + (ev.text || 'đã trả lời'); showTool(a, '✓ xong');
        a.hideT = setTimeout(() => hideTool(a), 1800);
        if (ev.text) log(a, esc(ev.text));
      }
      break;
    }
    case 'llm_error':
      if (!a) return; a.activity = 'idle'; showTool(a, '⚠ lỗi ' + (ev.status || '')); a.hideT = setTimeout(() => hideTool(a), 4000);
      a.status = 'Lỗi: ' + ev.message; log(a, '⚠ ' + esc(ev.message), 'k-err');
      break;
    case 'handoff': {
      const f = byId.get(ev.from), t = byId.get(ev.to); if (!f || !t) return; totals.handoffs++;
      if (!fast) burst(headPos(f), headPos(t), f.color, 7);
      t.lastActive = now;
      sys(`<b style="color:${f.color}">${esc(f.name)}</b> → <b style="color:${t.color}">${esc(t.name)}</b>${ev.via ? ` <small>qua <code>${esc(ev.via)}</code></small>` : ''}`);
      break;
    }
    case 'process':
      proc = ev;
      if (!fast) bossSays(ev.status === 'running' ? '▶ ' + shortCmd(ev.cmd) : ev.status === 'exited' ? `■ xong (exit ${ev.code})` : '⚠ ' + (ev.message || ev.status));
      sys(ev.status === 'running' ? `▶ Sếp chạy <code>${esc(shortCmd(ev.cmd))}</code>` : ev.status === 'exited' ? `■ Tiến trình kết thúc · exit ${ev.code}` : `⚠ ${esc(ev.message || '')}`);
      break;
    case 'message':
      if (a) log(a, esc(ev.text)); else sys(esc(ev.text));
      break;
    case 'status': // from /ingest: {type:'status', id, state:'think'|'tool'|'idle', text}
      if (!a) return; a.activity = ev.state || 'tool'; a.lastActive = now; if (ev.text) { showTool(a, ev.text); a.status = ev.text; }
      if (a.activity === 'idle') a.hideT = setTimeout(() => hideTool(a), 1500);
      break;
  }
}

// ================= boards =================
const kpi = board(4.6, 2.8, -HALF - 0.27, 0, 3.4, 1.7, (g, w, h) => {
  g.fillStyle = '#060c1f'; g.fillRect(0, 0, w, h);
  g.fillStyle = '#7f8bc4'; g.font = '600 22px system-ui'; g.fillText('AGENT OFFICE · LIVE', 22, 36);
  const wld = currentWorld();
  const active = wld ? wld.actors.filter(a => actorActivity(wld, a) !== 'idle').length : agents.filter(a => a.activity !== 'idle').length;
  const tk = totals.tokens >= 1000 ? (totals.tokens / 1000).toFixed(1) + 'k' : String(totals.tokens);
  [[active, 'đang làm', '#4fd8ff'], [totals.calls, 'LLM call', '#ffd36b'], [totals.tools, 'tool call', '#6bf29b'], [tk, 'token', '#ff7eb6']].forEach(([v, l, c], i) => {
    const x = 26 + i * (w - 40) / 4; g.fillStyle = c; g.font = '700 66px system-ui'; g.fillText(String(v), x, 146);
    g.fillStyle = '#8b95c4'; g.font = '20px system-ui'; g.fillText(l, x, 184);
  });
});
const barsBoard = board(-HALF - 0.27, 3.0, -5.6, Math.PI / 2, 3.2, 1.5, (g, w, h) => {
  g.fillStyle = '#060c1f'; g.fillRect(0, 0, w, h);
  const list = agents.slice(0, 20), value = a => currentWorld() ? a.tools : a.calls, max = Math.max(1, ...list.map(value));
  g.fillStyle = '#7f8bc4'; g.font = '600 18px system-ui'; g.fillText(currentWorld() ? 'Actions / agent (page)' : 'LLM calls / agent', 16, 26);
  list.forEach((a, i) => { const bw = (w - 32) / Math.max(8, list.length), v = value(a) / max;
    g.fillStyle = a.color; g.fillRect(16 + i * bw + 3, h - 14 - v * (h - 56), bw - 8, Math.max(3, v * (h - 56))); });
});
const rate = Array.from({ length: 48 }, () => 0);
let lastCalls = 0, rateT = 0;
const chartBoard = board(-4.8, 3.2, -HALF - 0.27, 0, 3.0, 1.4, (g, w, h) => {
  g.fillStyle = '#060c1f'; g.fillRect(0, 0, w, h);
  rateT++; if (rateT % 8 === 0) { rate.push(totals.calls - lastCalls); lastCalls = totals.calls; rate.shift(); }
  const m = Math.max(2, ...rate);
  g.strokeStyle = 'rgba(120,150,255,.15)'; for (let y = 30; y < h; y += 40) { g.beginPath(); g.moveTo(0, y); g.lineTo(w, y); g.stroke(); }
  g.strokeStyle = '#ffd36b'; g.lineWidth = 4; g.beginPath();
  rate.forEach((v, i) => { const x = 10 + i * (w - 20) / 47, y = h - 12 - (v / m) * (h - 30); i ? g.lineTo(x, y) : g.moveTo(x, y); }); g.stroke();
});
let sweep = 0;
const radarBoard = board(-HALF - 0.27, 3.0, 4.6, Math.PI / 2, 1.8, 1.8, (g, w, h) => {
  g.fillStyle = '#060c1f'; g.fillRect(0, 0, w, h); const cx = w / 2, cy = h / 2, R = w * 0.42;
  g.strokeStyle = 'rgba(107,242,155,.35)'; g.lineWidth = 2; for (let r = R / 3; r <= R; r += R / 3) { g.beginPath(); g.arc(cx, cy, r, 0, 7); g.stroke(); }
  sweep += 0.12; g.fillStyle = 'rgba(107,242,155,.35)'; g.beginPath(); g.moveTo(cx, cy); g.arc(cx, cy, R, sweep, sweep + 0.6); g.fill();
  agents.forEach((a, i) => { if (a.activity === 'idle') return; const an = i * 2.4, r = 0.3 + (i % 3) * 0.22; g.fillStyle = a.color; g.beginPath(); g.arc(cx + Math.cos(an) * R * r, cy + Math.sin(an) * R * r, 7, 0, 7); g.fill(); });
});

// ================= UI =================
const $log = document.getElementById('log'), $cards = document.getElementById('cards');
const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
let proc = null;
const shortCmd = c => String(c || '').replace(/(?:[A-Za-z]:)?[^\s]*[\/\\]([^\s\/\\]+)/g, '$1');
window.__office = { agents, byId, onEvent, currentWorld, worldHealth, selectAgent,
  deskScreenPoint(id) {
    const a = byId.get(id); if (!a?.desk) return null;
    const p = a.desk.g.localToWorld(new THREE.Vector3(0, 1.12, -0.196)).project(camera);
    const r = renderer.domElement.getBoundingClientRect();
    return { x: r.left + (p.x + 1) * r.width / 2, y: r.top + (1 - p.y) * r.height / 2 };
  } };
function feed(who, color, html, cls = '') {
  const d = document.createElement('div'); d.className = 'msg ' + cls;
  const tm = new Date().toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  d.innerHTML = `<div class="who"><span class="dot" style="background:${color}"></span>${esc(who)}<small>${tm}</small></div><div class="tx">${html}</div>`;
  const stick = $log.scrollHeight - $log.scrollTop - $log.clientHeight < 60;
  $log.appendChild(d); while ($log.children.length > 200) $log.firstChild.remove(); if (stick) $log.scrollTop = $log.scrollHeight;
}
const log = (a, html, cls) => feed(a.name, a.color, html, cls);
const sys = html => feed('Văn phòng', '#8993c2', html, 'k-sys');
function addCard(a) {
  const c = document.createElement('div'); c.className = 'card';
  c.innerHTML = `<div class="top"><span class="dot" style="background:${a.color};box-shadow:0 0 8px ${a.color}"></span><b></b><span class="rl"></span></div><div class="st"></div><div class="meta"></div>`;
  c.querySelector('b').textContent = a.name; c.querySelector('.rl').textContent = a.role;
  c.tabIndex = 0; c.setAttribute('role', 'button'); c.setAttribute('aria-label', `Xem hoạt động ${a.name}`);
  c.addEventListener('click', () => selectAgent(a));
  c.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); selectAgent(a); } });
  a.card = c; $cards.appendChild(c); document.getElementById('empty').style.display = 'none';
}
function ui() {
  renderActorDetail();
  for (const a of agents) {
    const c = a.card; c.querySelector('.st').textContent = a.status;
    c.querySelector('.meta').textContent = a.worldActor ? `${a.tools} hành động · tick ${a.worldActor.last_tick ?? '—'}` : `${a.calls} call · ${a.tools} tool · ${a.tokens >= 1000 ? (a.tokens / 1000).toFixed(1) + 'k' : a.tokens} tok`;
    c.classList.toggle('on', a.activity !== 'idle'); c.classList.toggle('sel', selected === a); c.classList.toggle('rest', a.where === 'lounge');
  }
  if (updateWorldUI()) return;
  document.getElementById('sAgents').textContent = agents.length;
  document.getElementById('sActive').textContent = agents.filter(a => a.activity !== 'idle').length;
  document.getElementById('sCalls').textContent = totals.calls;
  document.getElementById('sTools').textContent = totals.tools;
  const p = document.getElementById('proc');
  p.innerHTML = proc ? (proc.status === 'running' ? `<span class="run">●</span> <code>${esc(shortCmd(proc.cmd))}</code>` : `<span class="off">■</span> <code>${esc(shortCmd(proc.cmd))}</code> · exit ${esc(proc.code)}`) : 'Chưa có tiến trình — đang chờ…';
}
const $conn = document.getElementById('conn');
function setConn(ok, text) { $conn.className = 'live ' + (ok ? 'ok' : 'bad'); $conn.textContent = text || (ok ? '● viewer online' : '● mất kết nối viewer'); }
let boot = null, lastSeq = 0;
function connect() {
  const es = new EventSource('events');
  es.onopen = () => setConn(true);
  es.onerror = () => setConn(false);
  es.onmessage = e => {
    let ev; try { ev = JSON.parse(e.data); } catch (_) { return; }
    if (ev.type === 'hello') { if (boot && ev.boot !== boot) location.reload(); boot = ev.boot; return; }
    if (ev.type === 'replay_done') return;
    if (!['agent', 'world_snapshot'].includes(ev.type) && ev.seq && ev.seq <= lastSeq) return;
    if (ev.seq && ev.type !== 'agent') lastSeq = Math.max(lastSeq, ev.seq);
    try { onEvent(ev); } catch (err) { console.error(err); }
  };
}
if (location.protocol.startsWith('http')) connect();
else setConn(false, '● mở bằng agent-office');

// picking
const ray = new THREE.Raycaster(), mp = new THREE.Vector2();
function pickAgent(e) {
  const r = renderer.domElement.getBoundingClientRect();
  mp.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
  ray.setFromCamera(mp, camera);
  const hit = ray.intersectObjects(agents.flatMap(a => a.desk ? [a.robot, a.desk.g] : [a.robot]), true)[0];
  return hit ? hit.object.userData.agent : null;
}
let down = null;
renderer.domElement.addEventListener('pointerdown', e => { down = [e.clientX, e.clientY]; });
renderer.domElement.addEventListener('pointerup', e => { if (down && Math.hypot(e.clientX - down[0], e.clientY - down[1]) < 5) { selectAgent(pickAgent(e)); if (selected && selected.card) selected.card.scrollIntoView({ block: 'nearest', behavior: 'smooth' }); } down = null; });
let hoverT = 0;
renderer.domElement.addEventListener('pointermove', e => { if (performance.now() - hoverT < 60) return; hoverT = performance.now(); hovered = pickAgent(e); renderer.domElement.style.cursor = hovered ? 'pointer' : 'grab'; });
document.getElementById('toggleTeam').addEventListener('click', () => document.body.classList.toggle('team'));

// ================= loop =================
const clock = new THREE.Clock(); let T = 0, boardT = 0;
function frame() {
  const rawDt = Math.min(0.25, clock.getDelta()), dt = Math.min(0.05, rawDt); T += rawDt;
  for (const a of agents) {
    const r = a.robot;
    if (a.path.length) {
      const p = a.path[0], dx = p.x - r.position.x, dz = p.z - r.position.z, d = Math.hypot(dx, dz), st = 2.0 * rawDt;
      if (d > 0.01) r.rotation.y = lerpAngle(r.rotation.y, Math.atan2(-dx, -dz), 1 - Math.exp(-dt * 14));
      if (d <= st) { r.position.x = p.x; r.position.z = p.z; a.path.shift(); if (!a.path.length) { a.mode = 'stand'; const f = a.arrive; a.arrive = null; f && f(); } }
      else { r.position.x += dx / d * st; r.position.z += dz / d * st; }
    } else r.rotation.y = lerpAngle(r.rotation.y, a.faceTo, 1 - Math.exp(-dt * 8));
    animateRobot(r, a.mode, T, dt);
    const seated = a.mode === 'sit' || a.mode === 'type' || a.mode === 'lounge';
    a.nameL.position.y = seated ? 1.85 : 2.0; a.toolL.position.y = seated ? 2.4 : 2.55;
    if (a.slot && a.slot.sideX > 0) a.nameL.visible = selected === a || hovered === a;
    if (a.desk) {
      const on = a.desk.on;
      a.desk.scr.color.setScalar(THREE.MathUtils.lerp(a.desk.scr.color.r, on ? 1.5 : 0.28, 1 - Math.exp(-dt * 6)));
      if (on) a.desk.tex.offset.y -= dt * 0.25;
    }
  }
  animateRobot(boss, 'stand', T, dt);
  if (selected) { selRing.visible = true; selRing.position.set(selected.robot.position.x, 0.1, selected.robot.position.z); selRing.material.color.set(selected.color).multiplyScalar(2); }
  else selRing.visible = false;
  flare = Math.max(0, flare - dt * 0.7);
  orb.position.y = 1.4 + Math.sin(T * 1.6) * 0.06; halo.position.y = orb.position.y;
  orb.scale.setScalar(1 + flare * 0.25 + Math.sin(T * 3) * 0.02);
  halo.scale.setScalar(3.4 + flare * 2.2 + Math.sin(T * 2) * 0.15);
  orbLight.intensity = 18 + flare * 30;
  rings[0].rotation.set(T * 0.7, T * 0.4, 0); rings[1].rotation.set(-T * 0.5, 0, T * 0.6);
  rings.forEach(r => (r.position.y = orb.position.y));
  for (let i = pulses.length - 1; i >= 0; i--) { const p = pulses[i]; p.t += dt; p.m.scale.setScalar(1 + p.t * 2.2); p.m.material.opacity = Math.max(0, 1 - p.t / 1.2);
    if (p.t > 1.2) { core.remove(p.m); p.m.geometry.dispose(); p.m.material.dispose(); pulses.splice(i, 1); } }
  for (let i = parts.length - 1; i >= 0; i--) { const p = parts[i]; p.t += dt / 0.8;
    if (p.t >= 1) { scene.remove(p.s); p.s.material.dispose(); parts.splice(i, 1); continue; }
    const a = p.fromFn(), b = p.toFn(); p.s.position.lerpVectors(a, b, p.t); p.s.position.y += Math.sin(p.t * Math.PI) * 1.2; }
  starSets[0].material.opacity = 0.65 + Math.sin(T * 1.3) * 0.3; starSets[1].material.opacity = 0.65 + Math.cos(T * 0.9) * 0.3;
  boardT += dt; if (boardT > 0.12) { boardT = 0; for (const b of boards) { const { c, g } = b.t.userData; b.draw(g, c.width, c.height); b.t.needsUpdate = true; } }
  controls.update();
  composer.render(); labelR.render(scene, camera);
  requestAnimationFrame(frame);
}
layout(); frame(); setInterval(ui, 250); ui();
