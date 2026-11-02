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
    status: choice(v.status, ['running', 'stopped']), updated_at: number(v.updated_at), tick_seconds: number(v.tick_seconds),
    tick: number(v.tick), actors, trace: normalizeTrace(v.trace, actors, v.tick), actions: counters(v.actions, ACTIONS), llm: counters(v.llm),
    llm_by_team: Object.fromEntries(TEAMS.map(t => [t, counters(v.llm_by_team?.[t])])),
    key_layout: choice(v.key_layout, ['off', 'teams', 'shared']), pools, budget_exhausted: v.budget_exhausted === true };
}
module.exports = { normalizeSnapshot, MAX_BYTES };
