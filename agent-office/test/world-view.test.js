'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { worldHealth, actorActivity, actorStatus } = require('../viewer-src/world-state');
const { actorTrace, httpOutcome, describeTool, rangeEvidenceSummary } = require('../viewer-src/trace-view');
const { TEAM_ORDER, TEAM_ZONES, teamSeat, rosterPage } = require('../viewer-src/office-layout');

test('frozen telemetry becomes unknown, stopped remains stopped, resume becomes live', () => {
  const world = { status: 'running', updated_at: 100, tick_seconds: 2, tick: 10 };
  const actor = { activity: 'planning', last_tick: 10 };
  assert.equal(worldHealth(world, 110), 'running');
  assert.equal(actorActivity(world, actor, 110), 'think');
  assert.equal(worldHealth(world, 131), 'stale');
  assert.equal(actorActivity(world, actor, 131), 'idle');
  assert.equal(worldHealth({ ...world, status: 'stopped' }, 500), 'stopped');
  assert.equal(worldHealth({ ...world, updated_at: 500 }, 501), 'running');
  assert.equal(worldHealth({ ...world, tick_seconds: 60 }, 200), 'running');
});

test('every actor up to the runtime limit is accessible without overlapping desks', () => {
  const world = { actors: Array.from({ length: 200 }, (_, i) => ({ id: `actor-${i}`, team: i < 90 ? 'client' : i < 150 ? 'red' : 'blue' })) };
  for (const capacity of [12, 24]) {
    const seen = new Set();
    const pages = rosterPage(world, 'all', 0, capacity).pages;
    for (let page = 0; page < pages; page++) {
      const result = rosterPage(world, 'all', page, capacity);
      assert(result.items.length <= capacity * 3);
      for (const team of TEAM_ORDER) assert(result.items.filter(a => a.team === team).length <= capacity);
      result.items.forEach(a => { assert(!seen.has(a.id)); seen.add(a.id); });
    }
    assert.equal(seen.size, 200);
    const first = rosterPage(world, 'all', 0, capacity);
    assert.deepEqual([...new Set(first.items.map(a => a.team))], TEAM_ORDER);
    const onlyBlue = rosterPage(world, 'blue', 0, capacity);
    assert.deepEqual(onlyBlue.items, first.items.filter(a => a.team === 'blue'));
  }
  const blue = rosterPage(world, 'blue', 9);
  assert.equal(blue.page, 4); assert.equal(blue.items.length, 2);
  assert(blue.items.every(a => a.team === 'blue'));
  assert.equal(rosterPage({ actors: [] }).pages, 1);
});

test('72 team seats have separated desk/chair footprints and never cross zone boundaries', () => {
  const seats = TEAM_ORDER.flatMap(team => Array.from({ length: 24 }, (_, i) => teamSeat(team, i)));
  const labels = new Set();
  for (const seat of seats) {
    const zone = TEAM_ZONES[seat.team];
    assert(seat.x - seat.w / 2 > zone.x - 5 && seat.x + seat.w / 2 < zone.x + 5);
    assert(seat.z - 0.4 > -16.2 && seat.z + 1.4 < 0.6);
    assert(!labels.has(seat.label)); labels.add(seat.label);
    for (const other of seats) {
      if (other === seat) continue;
      assert(Math.abs(other.x - seat.x) >= 2 || Math.abs(other.z - seat.z) >= 2);
    }
  }
  assert.equal(labels.size, 72);
  assert.throws(() => teamSeat('blue', 24));
  assert.throws(() => teamSeat('unknown', 0));
  const oneTeam = { actors: Array.from({ length: 200 }, (_, i) => ({ id: String(i), team: 'red' })) };
  assert.equal(rosterPage(oneTeam, 'all', 0, 24).pages, 9);
  assert.equal(rosterPage(oneTeam, 'all', 8, 24).items.length, 8);
});

test('finished and waiting actors remain idle even with an inference pending', () => {
  const world = { status: 'running', updated_at: 100, tick_seconds: 2, tick: 10 };
  const actor = { activity: 'planning', last_tick: 10, control_status: 'WAITING', wake_tick: 15,
    active_specialty: 'network', active_task: 'task-000001', task_counts: { blocked: 1, done: 2 } };
  assert.equal(actorActivity(world, actor, 101), 'idle');
  assert.match(actorStatus(actor), /Chờ tới tick 15/);
  assert.match(actorStatus(actor), /network.*task-000001/);
  assert.match(actorStatus(actor), /vướng 1/);
  assert.match(actorStatus({ ...actor, control_status: 'DONE' }), /Đã hoàn tất/);
  assert.match(actorStatus({ ...actor, learning_counts: { episodes: 3, proposals: 2, published: 1 } }), /3 lượt.*2 đề xuất.*1 phát hành/);
});

test('actor detail links only case evidence, explicit case actions and direct targets', () => {
  const world = { trace: { events: [
    { id: 1, tick: 1, actor_id: 'red', tool: 'read_document' },
    { id: 2, tick: 1, actor_id: 'blue', tool: 'open_case', case_id: 'case-1' },
    { id: 3, tick: 1, actor_id: 'other-red', tool: 'read_document' },
    { id: 4, tick: 2, actor_id: 'blue', tool: 'contain', target_actor_id: 'red', case_id: 'case-1' },
    { id: 5, tick: 2, actor_id: 'other-blue', tool: 'restore', case_id: 'case-2' },
  ], cases: [
    { id: 'case-1', evidence_ids: [1], responses: [{ actor_id: 'blue' }] },
    { id: 'case-2', evidence_ids: [3], responses: [{ actor_id: 'other-blue' }] },
  ] } };
  const detail = actorTrace(world, 'red');
  assert.deepEqual(detail.own.map(e => e.id), [1]);
  assert.deepEqual(detail.events.map(e => e.id), [1, 2, 4]);
  assert.deepEqual(detail.cases.map(c => c.id), ['case-1']);
  assert.deepEqual(actorTrace(world, 'blue').events.map(e => e.id), [1, 2, 4]);
  assert.deepEqual(actorTrace(world, 'unknown').events, []);
  assert.equal(actorTrace({}, 'red'), null);
  assert.match(httpOutcome(403), /từ chối/);
  assert.doesNotMatch(httpOutcome(200), /tấn công|xâm nhập/);
});

test('skill lookup receipts never claim remote execution, including legacy exports and failures', () => {
  for (const status of [200, 400, 404, 409]) {
    const entry = { tool: 'consult_skill', result: { status, guidance_only: true }, evidence_complete: true };
    assert.match(rangeEvidenceSummary(entry), /Tra cứu hướng dẫn tại controller/);
    assert.doesNotMatch(rangeEvidenceSummary(entry), /Đã nhận và kiểm hash/);
  }
  assert.match(describeTool('consult_skill'), /không tự thực hiện/);
  assert.match(rangeEvidenceSummary({ tool: 'login', evidence_complete: true }), /Đã nhận và kiểm hash/);
  assert.match(rangeEvidenceSummary({ tool: 'login', evidence_complete: false }), /chưa đầy đủ/);
});
