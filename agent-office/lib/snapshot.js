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
function normalizeSnapshot(v) {
  if (!v || v.type !== 'world_snapshot' || v.schema_version !== 1 || !Array.isArray(v.actors) || v.actors.length > 200) throw new Error('Unsupported world snapshot');
  const actors = v.actors.map(a => ({
    id: word(a.id, 48), team: choice(a.team, TEAMS), role: word(a.role),
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
    tick: number(v.tick), actors, actions: counters(v.actions, ACTIONS), llm: counters(v.llm),
    llm_by_team: Object.fromEntries(TEAMS.map(t => [t, counters(v.llm_by_team?.[t])])),
    key_layout: choice(v.key_layout, ['off', 'teams', 'shared']), pools, budget_exhausted: v.budget_exhausted === true };
}
module.exports = { normalizeSnapshot, MAX_BYTES };
