'use strict';
// A separate protocol from proxy inference: values are cumulative runtime counters.
const TEAMS = ['client', 'red', 'blue'];
const USAGE = ['attempts', 'successes', 'input_tokens', 'output_tokens'];
const ACTIONS = ['actions_llm', 'actions_scripted', 'actions_scripted_fallback'];
const MAX_BYTES = 256 * 1024;
function number(v) { if (!Number.isFinite(v) || v < 0) throw new Error('Invalid snapshot number'); return v; }
function word(v, max = 80) { if (typeof v !== 'string' || !v.length || v.length > max) throw new Error('Invalid snapshot text'); return v; }
function choice(v, options) { if (!options.includes(v)) throw new Error('Invalid snapshot enum'); return v; }
function counters(v = {}, names = USAGE) { return Object.fromEntries(names.map(k => [k, number(v[k] ?? 0)])); }
function specialties(v = []) {
  if (!Array.isArray(v) || v.length > 12) throw new Error('Invalid specialties');
  return v.map(s => word(s, 40));
}
function integer(v, min = 0) {
  if (!Number.isSafeInteger(v) || v < min) throw new Error('Invalid trace integer');
  return v;
}
function boundedList(v, max) {
  if (!Array.isArray(v) || v.length > max) throw new Error('Invalid trace list');
  return v;
}
function normalizeNativePage(v) {
  const actor = word(v.actor_id, 48);
  if (!/^[a-zA-Z0-9_-]+$/.test(actor)) throw new Error('Invalid native actor');
  const tick = integer(v.through_tick), sensor = choice(v.sensor, ['saber-native-v1']);
  const fields = {
    'process.start': ['command_line', 'ppid'], 'process.exit': ['exit_code', 'error'],
    'dns.response': ['name', 'answer', 'server', 'transport', 'bytes'],
    'network.connect': ['local', 'remote', 'transport'],
    'http.response': ['method', 'path', 'status', 'bytes', 'duration_ms'],
    'file.write': ['path', 'bytes'], 'file.read': ['path', 'bytes', 'sha256'],
  };
  const numeric = new Set(['ppid', 'exit_code', 'bytes', 'status', 'duration_ms']);
  const events = boundedList(v.events, 100).map(e => {
    const kind = choice(e.kind, Object.keys(fields)), data = {};
    if (e.actor_id !== actor || e.sensor !== sensor || integer(e.tick) > tick) throw new Error('Invalid native provenance');
    for (const k of fields[kind]) {
      const value = e.data?.[k];
      if (value == null && k === 'error') { data[k] = null; continue; }
      if (numeric.has(k)) {
        if (!Number.isFinite(value) || (k !== 'exit_code' && value < 0)) throw new Error('Invalid native number');
        data[k] = value;
      } else { data[k] = word(value, k === 'command_line' ? 4096 : 256); }
    }
    return { id: integer(e.id, 1), actor_id: actor, tick: e.tick, sensor, kind, data,
      pid: integer(e.pid, 1), capture_id: word(e.capture_id, 64), ts: word(e.ts, 64),
      event_id: e.event_id == null ? null : integer(e.event_id, 1) };
  });
  if (events.some((e, i) => i && (e.id <= events[i - 1].id || e.tick < events[i - 1].tick))) throw new Error('Invalid native order');
  return { schema_version: choice(v.schema_version, [1]), world_id: word(v.world_id),
    actor_id: actor, through_tick: tick, limit: choice(v.limit, [100]), sensor, events };
}
function normalizeTrace(v, actors, tick) {
  if (v == null) return null; // Older snapshots have no history; never fabricate it.
  const ids = new Set(actors.map(a => a.id));
  const actor = id => { if (!ids.has(id)) throw new Error('Unknown trace actor'); return id; };
  const at = value => { if (integer(value) > tick) throw new Error('Future trace'); return value; };
  const target = value => value === '' ? '' : word(value, 160);
  const events = boundedList(v.events, 200).map(e => ({
    id: integer(e.id, 1), tick: at(e.tick), actor_id: actor(e.actor_id),
    tool: word(e.tool), target: target(e.target), status: integer(e.status, 100),
    target_actor_id: e.target_actor_id == null ? null : actor(e.target_actor_id),
    source: choice(e.source, ['unknown', 'llm', 'scripted', 'scripted-fallback']),
    case_id: e.case_id == null ? null : word(e.case_id),
  }));
  if (events.some((e, i) => e.status > 599 || (i && (e.id <= events[i - 1].id || e.tick < events[i - 1].tick)))) throw new Error('Invalid trace order/status');
  const eventIds = new Set(events.map(e => e.id));
  const cases = boundedList(v.cases, 12).map(c => ({
    id: word(c.id), status: choice(c.status, ['OPEN', 'INVESTIGATING', 'MITIGATED', 'CLOSED']),
    evidence_count: integer(c.evidence_count),
    evidence_ids: boundedList(c.evidence_ids, 50).map(id => {
      if (!eventIds.has(id)) throw new Error('Unknown trace evidence'); return id;
    }),
    responses: boundedList(c.responses, 8).map(r => ({
      actor_id: actor(r.actor_id), tick: at(r.tick), tool: word(r.tool), target: target(r.target),
      verified: choice(r.verified, [true, false]),
    })),
  }));
  if (new Set(cases.map(c => c.id)).size !== cases.length || cases.some(c => c.evidence_count < c.evidence_ids.length)) throw new Error('Invalid trace cases');
  return { limit: choice(v.limit, [200]), events, cases };
}
function normalizeSnapshot(v) {
  if (!v || v.type !== 'world_snapshot' || v.schema_version !== 1 || !Array.isArray(v.actors) || v.actors.length > 200) throw new Error('Unsupported world snapshot');
  const actors = v.actors.map(a => ({
    id: word(a.id, 48), team: choice(a.team, TEAMS), role: word(a.role),
    specialties: specialties(a.specialties),
    control_status: choice(a.control_status ?? 'ACTIVE', ['ACTIVE', 'WAITING', 'DONE']),
    wake_tick: a.wake_tick == null ? null : number(a.wake_tick),
    active_specialty: a.active_specialty == null ? a.role : word(a.active_specialty, 40),
    active_task: a.active_task == null ? null : word(a.active_task, 80),
    task_counts: counters(a.task_counts, ['offered', 'active', 'blocked', 'done']),
    learning_counts: counters(a.learning_counts, ['episodes', 'proposals', 'published']),
    activity: choice(a.activity, ['idle', 'planning']), turns: number(a.turns),
    last_tick: a.last_tick == null ? null : number(a.last_tick),
    last_tool: a.last_tool == null ? null : word(a.last_tool),
    last_status: a.last_status == null ? null : number(a.last_status),
    source: choice(a.source, ['none', 'llm', 'scripted', 'scripted-fallback']),
    ...(a.executor ? { executor: {
      host: a.executor.host == null ? null : word(a.executor.host, 80),
      pid: a.executor.pid == null ? null : integer(a.executor.pid, 1),
      job_id: a.executor.job_id == null ? null : word(a.executor.job_id, 36),
      exit_code: a.executor.exit_code == null ? null : integer(a.executor.exit_code, -255),
      pending: a.executor.pending === true,
      artifacts: boundedList(a.executor.artifacts ?? [], 12).map(f => ({
        name: choice(f.name, ['browser.png', 'read-document.txt', 'collected.txt', 'evidence.json', 'analysis.json', 'case-evidence.json', 'case-timeline.json', 'rule-evaluation.json']),
        bytes: integer(f.bytes), sha256: /^[a-f0-9]{64}$/.test(f.sha256) ? f.sha256 : (() => { throw new Error('Invalid artifact digest'); })(),
      })),
    }} : {}),
  }));
  if (new Set(actors.map(a => a.id)).size !== actors.length) throw new Error('Duplicate actor');
  const pools = {};
  for (const team of TEAMS) {
    const p = v.pools?.[team]; if (!p) continue;
    pools[team] = { model: word(p.model, 100), first_key: number(p.first_key), last_key: number(p.last_key),
      keys: number(p.keys), active_key: p.active_key == null ? null : number(p.active_key), state: word(p.state, 40) };
  }
  return { type: 'world_snapshot', schema_version: 1, world_id: word(v.world_id), run_id: word(v.run_id),
    profile: choice(v.profile, ['local', 'sandbox', 'vm', 'remote']), engine: choice(v.engine, ['scripted', 'hybrid']),
    execution_mode: choice(v.execution_mode ?? 'unknown', ['application', 'native', 'range', 'unknown']),
    status: choice(v.status, ['running', 'stopped']), updated_at: number(v.updated_at), tick_seconds: number(v.tick_seconds),
    tick: number(v.tick), actors, trace: normalizeTrace(v.trace, actors, v.tick), actions: counters(v.actions, ACTIONS), llm: counters(v.llm),
    llm_by_team: Object.fromEntries(TEAMS.map(t => [t, counters(v.llm_by_team?.[t])])),
    key_layout: choice(v.key_layout, ['off', 'teams', 'shared']), pools, budget_exhausted: v.budget_exhausted === true };
}
const RANGE_BYTES = 2_000_000;
function publicData(value, depth = 0) {
  if (depth > 16) throw new Error('Excessive evidence nesting');
  if (Array.isArray(value)) return boundedList(value, 1000).map(v => publicData(v, depth + 1));
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).filter(([k]) => !/password|token|authorization|api_key|secret|credential/i.test(k)).map(([k, v]) => [k, publicData(v, depth + 1)]));
  if (typeof value === 'string') return value.replace(/AIza[\w-]{25,}/g, '[REDACTED]').replace(/((?:password|token|api[_-]?key|secret)[\s=:]+)\S+/gi, '$1[REDACTED]').slice(0, 16384);
  if (value == null || typeof value === 'boolean' || (typeof value === 'number' && Number.isFinite(value))) return value;
  throw new Error('Invalid evidence value');
}
function normalizeRangePage(v) {
  const actor = word(v.actor_id, 48), tick = integer(v.through_tick);
  if (!/^[a-zA-Z0-9_-]+$/.test(actor)) throw new Error('Invalid range actor');
  const digest = v => { if (!/^[a-f0-9]{64}$/.test(v)) throw new Error('Invalid evidence digest'); return v; };
  const id = v => { if (!/^[a-f0-9-]{32,36}$/.test(v)) throw new Error('Invalid job/evidence id'); return v; };
  const at = v => { if (integer(v) > tick) throw new Error('Future range evidence'); return v; };
  const entries = boundedList(v.entries, 12).map(e => ({
    job_id: id(e.job_id), tick: at(e.tick), event_id: integer(e.event_id, 1),
    tool: word(e.tool), source: choice(e.source, ['llm', 'scripted', 'scripted-fallback']),
    result: publicData(e.result), evidence_complete: e.evidence_complete === true,
    artifacts: boundedList(e.artifacts, 12).map(a => ({ name: word(a.name, 64), bytes: integer(a.bytes), sha256: digest(a.sha256) })),
    evidence: boundedList(e.evidence, 10).map(p => ({
      sha256: digest(p.sha256), hash_verified: p.hash_verified === true, display_redacted: true,
      event: { id: id(p.event.id), ts: word(p.event.ts, 64), host: word(p.event.host),
        kind: word(p.event.kind), sensor: word(p.event.sensor), data: publicData(p.event.data) },
    })),
  }));
  if (entries.some((e, i) => i && e.event_id <= entries[i - 1].event_id)) throw new Error('Invalid range order');
  let screen = null;
  if (v.screen) {
    const crypto = require('node:crypto'), s = v.screen;
    if (typeof s.png !== 'string' || s.png.length > 1_333_336 || !/^[A-Za-z0-9+/]*={0,2}$/.test(s.png)) throw new Error('Invalid screenshot');
    const bytes = Buffer.from(s.png, 'base64');
    if (bytes.length > 1_000_000 || !bytes.subarray(0, 8).equals(Buffer.from('89504e470d0a1a0a', 'hex')) || crypto.createHash('sha256').update(bytes).digest('hex') !== digest(s.sha256)) throw new Error('Screenshot integrity failure');
    screen = { job_id: id(s.job_id), tick: at(s.tick), sha256: s.sha256, png: bytes.toString('base64') };
  }
  return { schema_version: choice(v.schema_version, [1]), world_id: word(v.world_id),
    actor_id: actor, through_tick: tick, limit: choice(v.limit, [12]), entries, screen };
}
module.exports = { normalizeSnapshot, normalizeNativePage, normalizeRangePage, MAX_BYTES, RANGE_BYTES };
