'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const { createOffice } = require('../lib/server');
const { normalizeSnapshot, normalizeNativePage, normalizeRangePage, MAX_BYTES } = require('../lib/snapshot');
const { snapshotSource, watchSnapshots } = require('../lib/watch');

function fixture(overrides = {}) {
  return { type: 'world_snapshot', schema_version: 1, world_id: 'world-1', run_id: 'run-1',
    profile: 'sandbox', engine: 'hybrid', status: 'running', updated_at: Date.now() / 1000,
    tick_seconds: 2, tick: 8, key_layout: 'teams', budget_exhausted: false,
    actors: [{ id: 'client-1', team: 'client', role: 'employee', activity: 'idle', turns: 8,
      last_tick: 8, last_tool: 'browse', last_status: 200, source: 'scripted-fallback' }],
    llm: { attempts: 7, successes: 5, input_tokens: 70, output_tokens: 25 },
    llm_by_team: { client: { attempts: 7, successes: 5 } },
    actions: { actions_scripted_fallback: 8 },
    pools: { client: { model: 'fake', first_key: 1, last_key: 200, keys: 200, active_key: 2, state: 'ready' } },
    ...overrides };
}

test('snapshot validation bounds the roster and strips private data', () => {
  assert.equal(normalizeSnapshot(fixture()).execution_mode, 'unknown');
  assert.equal(normalizeSnapshot(fixture({ execution_mode: 'application' })).execution_mode, 'application');
  assert.equal(normalizeSnapshot(fixture({ execution_mode: 'native' })).execution_mode, 'native');
  assert.equal(normalizeSnapshot(fixture({ execution_mode: 'range' })).execution_mode, 'range');
  const input = fixture({ credential: 'SECRET', documents: ['PRIVATE'] });
  input.actors[0].note = 'PRIVATE'; input.pools.client.key = 'SECRET';
  input.actors[0].learning_counts = { episodes: 3, proposals: 2, published: 1, lesson: 'PRIVATE' };
  const value = normalizeSnapshot(input);
  assert.equal(value.llm.attempts, 7);
  assert.equal(value.pools.client.active_key, 2);
  assert.deepEqual(value.actors[0].learning_counts, { episodes: 3, proposals: 2, published: 1 });
  assert.doesNotMatch(JSON.stringify(value), /SECRET|PRIVATE/);
  assert.throws(() => normalizeSnapshot(fixture({ actors: Array(201).fill(input.actors[0]) })));
  assert.throws(() => normalizeSnapshot(fixture({ actors: [input.actors[0], input.actors[0]] })));
  assert.throws(() => normalizeSnapshot(fixture({ tick: NaN })));
  assert.throws(() => normalizeSnapshot(fixture({ schema_version: 2 })));
});

function nativeFixture(overrides = {}) {
  return { schema_version: 1, world_id: 'world-1', actor_id: 'client-1', through_tick: 8,
    limit: 100, sensor: 'saber-native-v1', events: [{ id: 1, actor_id: 'client-1', tick: 8,
      sensor: 'saber-native-v1', kind: 'process.start', pid: 123, capture_id: 'capture-1',
      ts: '2026-11-02T00:00:00Z', event_id: 4,
      data: { command_line: 'python -I -B native_worker.py', ppid: 12, token: 'SECRET' } }], ...overrides };
}

test('range evidence validates screen hashes, isolates actors and strips credentials', async t => {
  const crypto = require('node:crypto');
  const id = '12345678-1234-1234-1234-123456789abc';
  const png = Buffer.from('89504e470d0a1a0a00000000', 'hex');
  const page = { schema_version: 1, world_id: 'world-1', actor_id: 'client-1', through_tick: 8, limit: 12,
    entries: [{ job_id: id, tick: 8, event_id: 1, tool: 'browse', source: 'scripted',
      result: { pid: 10, token: 'PRIVATE' }, artifacts: [], evidence_complete: true,
      evidence: [{ sha256: 'a'.repeat(64), hash_verified: true, event: { id, ts: new Date().toISOString(), host: 'client', kind: 'process.launch', sensor: 'test', data: { pid: 10, authorization: 'PRIVATE' } } }] }],
    screen: { job_id: id, tick: 8, sha256: crypto.createHash('sha256').update(png).digest('hex'), png: png.toString('base64') } };
  assert.doesNotMatch(JSON.stringify(normalizeRangePage(page)), /PRIVATE|authorization|token/);
  assert.throws(() => normalizeRangePage({ ...page, screen: { ...page.screen, sha256: '0'.repeat(64) } }));
  assert.throws(() => normalizeRangePage({ ...page, through_tick: 7 }));
  assert.throws(() => normalizeRangePage({ ...page, entries: Array(13).fill(page.entries[0]) }));
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'office-range-'));
  const folder = path.join(dir, 'range-office'); await fs.mkdir(folder);
  const file = path.join(folder, 'client-1.json');
  await fs.writeFile(file, JSON.stringify(page));
  await fs.writeFile(path.join(dir, 'office.json'), JSON.stringify(fixture({ execution_mode: 'range' })));
  t.after(async () => { await fs.unlink(file); await fs.rmdir(folder); await fs.unlink(path.join(dir, 'office.json')); await fs.rmdir(dir); });
  const read = await snapshotSource({ world: dir });
  await assert.rejects(() => read.range('../keys_pool'));
  const { server, emit } = createOffice({ readOnly: true, readRange: read.range });
  emit(await read()); await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  t.after(() => { server.closeAllConnections(); server.close(); });
  const base = `http://127.0.0.1:${server.address().port}/range-events?world=world-1&actor=`;
  assert.equal((await fetch(base + 'client-1')).status, 200);
  assert.doesNotMatch(await (await fetch(base + 'client-1')).text(), /PRIVATE/);
  assert.equal((await fetch(base + 'unknown')).status, 404);
  await fs.writeFile(file, JSON.stringify({ ...page, world_id: 'other' }));
  assert.equal((await fetch(base + 'client-1')).status, 404);
});

test('native protocol keeps measured fields and rejects future or mixed-actor evidence', () => {
  const data = nativeFixture();
  assert.doesNotMatch(JSON.stringify(normalizeNativePage(data)), /SECRET/);
  assert.throws(() => normalizeNativePage({ ...data, through_tick: 7 }));
  assert.throws(() => normalizeNativePage({ ...data, actor_id: 'other' }));
  assert.throws(() => normalizeNativePage({ ...data, actor_id: '../keys_pool' }));
  assert.throws(() => normalizeNativePage({ ...data, events: [data.events[0], data.events[0]] }));
  assert.throws(() => normalizeNativePage({ ...data, events: Array(101).fill(data.events[0]) }));
});

test('native watch reads only per-actor public exports and scopes HTTP reads to known world actors', async t => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'office-native-'));
  const folder = path.join(dir, 'native-office'); await fs.mkdir(folder);
  const file = path.join(folder, 'client-1.json');
  t.after(async () => {
    await fs.unlink(file); await fs.rmdir(folder);
    await fs.unlink(path.join(dir, 'office.json')); await fs.rmdir(dir);
  });
  await fs.writeFile(file, JSON.stringify(nativeFixture()));
  await fs.writeFile(path.join(dir, 'office.json'), JSON.stringify(fixture({ execution_mode: 'native' })));
  const read = await snapshotSource({ world: dir });
  assert.equal((await read.native('client-1')).events[0].pid, 123);
  await assert.rejects(() => read.native('../keys_pool'));
  const { server, emit } = createOffice({ readOnly: true, readNative: read.native });
  emit(await read());
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  t.after(() => { server.closeAllConnections(); server.close(); });
  const base = `http://127.0.0.1:${server.address().port}/native-events?world=world-1&actor=`;
  const response = await fetch(base + 'client-1'); assert.equal(response.status, 200);
  assert.doesNotMatch(await response.text(), /SECRET/);
  assert.equal((await fetch(base + 'unknown')).status, 404);
  assert.equal((await fetch(base + '../keys_pool')).status, 404);
  await fs.writeFile(file, JSON.stringify(nativeFixture({ world_id: 'another-world' })));
  assert.equal((await fetch(base + 'client-1')).status, 404);
  await fs.writeFile(file, JSON.stringify(nativeFixture({ through_tick: 9,
    events: nativeFixture().events.map(e => ({ ...e, tick: 9 })) })));
  assert.deepEqual((await (await fetch(base + 'client-1')).json()).events, []);
});

test('optional execution traces retain evidence links and reject forged references', () => {
  assert.equal(normalizeSnapshot(fixture()).trace, null);
  const input = fixture({ trace: { limit: 200,
    events: [{ id: 4, tick: 8, actor_id: 'client-1', tool: 'read_document', target: 'welcome',
      status: 200, source: 'unknown', args: { token: 'SECRET' }, result: 'PRIVATE BODY' }],
    cases: [{ id: 'case-1', status: 'OPEN', evidence_ids: [4], evidence_count: 1,
      summary: 'PRIVATE', responses: [{ actor_id: 'client-1', tick: 8, tool: 'restore', target: 'business-app', verified: false, note: 'PRIVATE' }] }],
  } });
  const value = normalizeSnapshot(input);
  assert.equal(value.trace.events[0].id, 4);
  assert.deepEqual(value.trace.cases[0].evidence_ids, [4]);
  assert.equal(value.trace.cases[0].responses[0].verified, false);
  assert.doesNotMatch(JSON.stringify(value), /SECRET|PRIVATE/);
  for (const patch of [{ actor_id: 'other-world-actor' }, { tick: 9 }, { source: 'claimed-llm' }, { status: 900 }]) {
    const copy = structuredClone(input); Object.assign(copy.trace.events[0], patch);
    assert.throws(() => normalizeSnapshot(copy));
  }
  const copy = structuredClone(input); copy.trace.cases[0].evidence_ids = [999];
  assert.throws(() => normalizeSnapshot(copy));
  assert.throws(() => normalizeSnapshot(fixture({ trace: { ...input.trace, events: Array(201).fill(input.trace.events[0]) } })));
  assert.throws(() => normalizeSnapshot(fixture({ trace: { ...input.trace, events: [...input.trace.events, ...input.trace.events] } })));
});

test('HTTP ingestion, latest state, SSE replay and legacy events coexist', async t => {
  const { server, emit } = createOffice({ upstreams: {} });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  t.after(() => { server.closeAllConnections(); server.close(); });
  const base = `http://127.0.0.1:${server.address().port}`;
  const post = value => fetch(base + '/ingest', { method: 'POST', body: JSON.stringify(value) });
  assert.equal((await post(fixture())).status, 204);
  assert.equal((await post(fixture({ updated_at: 1, tick: 0 }))).status, 204);
  assert.equal((await post(fixture({ tick: -1 }))).status, 400);
  assert.equal((await post({ type: 'world_snapshot', extra: 'x'.repeat(MAX_BYTES) })).status, 413);
  // Older snapshot seq must still be replayed alongside newer legacy history.
  emit({ type: 'agent', id: 'legacy', name: 'Legacy' });
  emit({ type: 'tool', id: 'legacy', name: 'search' });
  const { worlds } = await (await fetch(base + '/state')).json();
  assert.equal(worlds.length, 1); assert.equal(worlds[0].tick, 8);
  const controller = new AbortController();
  const response = await fetch(base + '/events', { signal: controller.signal });
  const reader = response.body.getReader(); let text = '';
  while (!text.includes('replay_done')) text += new TextDecoder().decode((await reader.read()).value);
  controller.abort();
  assert.equal((text.match(/world_snapshot/g) || []).length, 1);
  assert.match(text, /legacy/); assert.match(text, /"attempts":7/);
  for (let i = 0; i < 25; i++) emit(fixture({ world_id: `world-${i}` }));
  assert.equal((await (await fetch(base + '/state')).json()).worlds.length, 16);
});

test('local watch survives missing files and publishes stopped/resumed state', async t => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'office-test-'));
  const file = path.join(dir, 'office.json');
  t.after(async () => { await fs.unlink(file).catch(() => {}); await fs.rmdir(dir); });
  const read = await snapshotSource({ world: dir });
  await assert.rejects(read);
  await fs.writeFile(file, JSON.stringify(fixture()));
  assert.equal((await read()).tick, 8);
  await fs.writeFile(file, JSON.stringify(fixture({ status: 'stopped' })));
  assert.equal((await read()).status, 'stopped');
  await fs.writeFile(file, JSON.stringify(fixture({ run_id: 'resume-2', tick: 9 })));
  assert.equal((await read()).run_id, 'resume-2');
  await fs.writeFile(file, 'x'.repeat(MAX_BYTES + 1)); await assert.rejects(read);
});

test('watch server rejects proxy requests and external ingestion', async t => {
  const { server } = createOffice({ readOnly: true });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  t.after(() => { server.closeAllConnections(); server.close(); });
  const base = `http://127.0.0.1:${server.address().port}`;
  assert.equal((await fetch(base + '/ingest', { method: 'POST', body: '{}' })).status, 405);
  assert.equal((await fetch(base + '/openai/models')).status, 405);
  assert.equal((await fetch(base + '/state')).status, 200);
});

test('sandbox watch uses fixed read-only docker commands and unique container selection', async t => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'office-bundle-'));
  const file = path.join(dir, 'bundle-manifest.json');
  t.after(async () => { await fs.unlink(file); await fs.rmdir(dir); });
  await fs.writeFile(file, JSON.stringify({ schema_version: 1, profile: 'sandbox', project: 'lab-123' }));
  const calls = [];
  const exec = async (cmd, args, options) => {
    calls.push(args); assert.equal(cmd, 'docker'); assert.equal(options.windowsHide, true);
    if (args[0] === 'ps') return { stdout: 'abc123def456\n' };
    assert.deepEqual(args.slice(0, 2), ['cp', 'abc123def456:/data/office.json']);
    await fs.writeFile(args[2], JSON.stringify(fixture())); return { stdout: '' };
  };
  const read = await snapshotSource({ bundle: dir, exec });
  assert.equal((await read()).profile, 'sandbox');
  assert.deepEqual(calls[0], ['ps', '-a', '--filter', 'label=com.docker.compose.project=lab-123', '--filter', 'label=com.docker.compose.service=world', '--format', '{{.ID}}']);
  const ambiguous = await snapshotSource({ bundle: dir, exec: async () => ({ stdout: 'abc123def456\ndef123abc456' }) });
  await assert.rejects(ambiguous);
  await fs.writeFile(file, JSON.stringify({ schema_version: 1, profile: 'sandbox', project: 'bad; command' }));
  await assert.rejects(() => snapshotSource({ bundle: dir, exec }));
  await assert.rejects(() => snapshotSource({ bundle: dir, world: dir }));
});

test('watch retries without overlapping reads or repeating identical snapshots', async () => {
  let active = 0, peak = 0, reads = 0; const events = [], messages = [];
  const value = fixture();
  const stop = watchSnapshots(async () => {
    active++; peak = Math.max(peak, active); reads++;
    await new Promise(r => setTimeout(r, 10)); active--;
    if (reads === 1) throw new Error('private failure');
    return value;
  }, e => events.push(e), { interval: 5, log: m => messages.push(m) });
  await new Promise(r => setTimeout(r, 100)); stop();
  assert.equal(peak, 1); assert.equal(events.length, 1);
  assert.equal(messages.length, 2); assert.doesNotMatch(messages.join(' '), /private failure/);
});
