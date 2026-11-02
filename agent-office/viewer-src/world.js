import { worldHealth, rosterPage, actorActivity, actorStatus } from './world-state.js';

const worlds = new Map();
let worldId = null, teamFilter = 'all', worldPage = 0, viewKey = '';
const teamColors = { client: '#4fd8ff', red: '#ff5c5c', blue: '#6bf29b' };
const teamNames = { client: 'Clients', red: 'Red Team', blue: 'Blue Team' };
const $worldSelect = document.getElementById('worldSelect');
const $teamFilter = document.getElementById('teamFilter');
const $worldPanel = document.getElementById('worldPanel');
const $teamMetrics = document.getElementById('teamMetrics');
const currentWorld = () => worlds.get(worldId);
const short = n => Number(n || 0).toLocaleString('vi-VN');

function clearOfficeActors() {
  selected = hovered = null;
  for (const a of agents) {
    a.removed = true; clearTimeout(a.hideT);
    if (a.arrive) { a.arrive(); a.arrive = null; }
    a.robot.removeFromParent(); a.nameL.element.remove(); a.toolL.element.remove();
    const materials = new Set();
    a.robot.traverse(o => { if (o.isMesh) { o.geometry.dispose(); materials.add(o.material); } });
    for (const m of materials) if (![white, jointM, visorM].includes(m)) m.dispose();
    if (a.slot) { a.slot.used = null; a.desk.g.visible = false; }
    if (a.floor) a.floor.used = null;
    if (a.sofa) a.sofa.used = null;
    a.card.remove();
  }
  agents.length = 0; byId.clear();
}

function receiveWorld(ev) {
  const previous = worlds.get(ev.world_id);
  if (previous && ev.updated_at <= previous.updated_at) return;
  if (!worlds.has(ev.world_id) && worlds.size >= 16) {
    const oldest = worlds.keys().next().value; worlds.delete(oldest);
    if (oldest === worldId) worldId = ev.world_id;
  }
  worlds.set(ev.world_id, ev);
  if (!worldId) worldId = ev.world_id;
  $worldSelect.replaceChildren(...[...worlds.values()].map(w => {
    const option = document.createElement('option'); option.value = w.world_id;
    option.textContent = `${w.profile} · ${w.world_id.slice(0, 8)}`; return option;
  }));
  $worldSelect.value = worldId;
  if (ev.world_id !== worldId) return;
  if (!previous || previous.run_id !== ev.run_id) sys(`World <code>${esc(ev.world_id.slice(0, 8))}</code> · ${esc(ev.profile)} · ${esc(ev.engine)} · tick ${ev.tick}`);
  renderWorld();
}

function renderWorld() {
  const w = currentWorld(); if (!w) return;
  $worldPanel.hidden = false; $teamMetrics.hidden = false;
  const page = rosterPage(w, teamFilter, worldPage); worldPage = page.page;
  const key = JSON.stringify([w.world_id, w.run_id, page.items.map(a => a.id)]);
  if (viewKey !== key) {
    clearOfficeActors(); viewKey = key;
    for (const a of page.items) createAgent({ id: `${w.world_id}/${a.id}`, name: a.id, role: `${teamNames[a.team]} / ${(a.specialties?.length ? a.specialties : [a.role]).join(', ')}`, color: teamColors[a.team], replay: true });
  }
  document.getElementById('pageInfo').textContent = `${page.page + 1}/${page.pages} · ${page.count} agent`;
  document.getElementById('prevPage').disabled = page.page === 0;
  document.getElementById('nextPage').disabled = page.page === page.pages - 1;
  document.getElementById('empty').style.display = page.count ? 'none' : 'block';
  for (const actor of page.items) {
    const a = byId.get(`${w.world_id}/${actor.id}`);
    const changed = a.worldActor && actor.turns > a.worldActor.turns;
    a.worldActor = actor; a.tools = actor.turns;
    a.activity = actorActivity(w, actor);
    a.status = `${actorStatus(actor)} · ${actor.source} · ${actor.last_tool || 'chưa có hành động'}${actor.last_status == null ? '' : ' · HTTP ' + actor.last_status}`;
    if (actor.activity === 'planning' && (actor.control_status ?? 'ACTIVE') === 'ACTIVE' && worldHealth(w) === 'running') a.status = 'Chờ / đang suy luận · ' + a.status;
    if (a.activity !== 'idle') a.lastActive = performance.now();
    if (changed) log(a, `<code>${esc(actor.last_tool)}</code> · ${esc(actor.source)} · HTTP ${actor.last_status} · tick ${actor.last_tick}`, 'k-tool');
  }
  totals.calls = w.llm.attempts; totals.tokens = w.llm.input_tokens + w.llm.output_tokens;
  totals.tools = Object.values(w.actions).reduce((sum, n) => sum + n, 0);
  updateWorldUI();
}

function updateWorldUI() {
  const w = currentWorld(); if (!w) return false;
  const health = worldHealth(w), stale = health === 'stale', stopped = health === 'stopped';
  if (stale || stopped) for (const a of agents) a.activity = 'idle';
  const age = Math.max(0, Math.floor(Date.now() / 1000 - w.updated_at));
  document.getElementById('proc').textContent = `${w.profile} · ${w.engine === 'scripted' ? 'Scripted' : 'Gemini + fallback'} · tick ${short(w.tick)}`;
  const state = document.getElementById('worldStatus');
  state.textContent = `${stopped ? 'Đã dừng' : stale ? 'Mất cập nhật — chưa rõ runtime' : 'Đang chạy'} · cập nhật ${age}s trước`;
  state.className = stale ? 'off' : stopped ? 'muted' : 'run';
  document.getElementById('sAgents').textContent = w.actors.length;
  document.getElementById('sActive').textContent = w.actors.filter(a => actorActivity(w, a) !== 'idle').length;
  document.getElementById('sCalls').textContent = short(w.llm.attempts);
  document.getElementById('sTools').textContent = short(totals.tools);
  document.getElementById('worldUsage').textContent = `LLM: ${short(w.llm.successes)}/${short(w.llm.attempts)} thành công · ${short(totals.tokens)} token${w.budget_exhausted ? ' · hết ngân sách → scripted' : ''}`;
  document.getElementById('actionSources').textContent = `Hành động: ${short(w.actions.actions_llm)} LLM · ${short(w.actions.actions_scripted)} scripted · ${short(w.actions.actions_scripted_fallback)} fallback`;
  $teamMetrics.innerHTML = Object.keys(teamNames).map(team => {
    const actors = w.actors.filter(a => a.team === team), u = w.llm_by_team[team], p = w.pools[team];
    const pool = p ? `Key #${p.active_key ?? '—'} · dải ${p.first_key}–${p.last_key} (${p.keys})<br>${esc(p.state)} · ${esc(p.model)}` : w.key_layout === 'off' ? 'LLM tắt' : 'Pool dùng chung';
    return `<div class="team-summary" style="--team:${teamColors[team]}"><b>${teamNames[team]} <span>${actors.length} agent</span></b><div>${short(u.successes)}/${short(u.attempts)} LLM thành công · ${short(u.input_tokens + u.output_tokens)} token</div><div>${pool}</div></div>`;
  }).join('');
  return true;
}

$worldSelect.addEventListener('change', () => { worldId = $worldSelect.value; worldPage = 0; renderWorld(); });
$teamFilter.addEventListener('change', () => { teamFilter = $teamFilter.value; worldPage = 0; renderWorld(); });
document.getElementById('prevPage').addEventListener('click', () => { worldPage--; renderWorld(); });
document.getElementById('nextPage').addEventListener('click', () => { worldPage++; renderWorld(); });
