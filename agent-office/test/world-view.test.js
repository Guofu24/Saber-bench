'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { worldHealth, rosterPage, actorActivity } = require('../viewer-src/world-state');

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
  const seen = new Set();
  for (let page = 0; page < 10; page++) {
    const result = rosterPage(world, 'all', page);
    assert.equal(result.pages, 10); assert.equal(result.items.length, 20);
    result.items.forEach(a => seen.add(a.id));
  }
  assert.equal(seen.size, 200);
  const blue = rosterPage(world, 'blue', 9);
  assert.equal(blue.page, 2); assert.equal(blue.items.length, 10);
  assert(blue.items.every(a => a.team === 'blue'));
  assert.equal(rosterPage({ actors: [] }).pages, 1);
});
