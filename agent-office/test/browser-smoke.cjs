// Optional real-browser check. Supply playwright-core externally; no runtime dependency.
// node test/browser-smoke.cjs PATH_TO_OFFICE_JSON ARTIFACT_DIRECTORY
const fs = require('node:fs/promises');
const path = require('node:path');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright-core');
const { createOffice } = require('../lib/server');

async function main() {
  const source = JSON.parse(await fs.readFile(process.argv[2], 'utf8'));
  const out = path.resolve(process.argv[3]); await fs.mkdir(out, { recursive: true });
  const { server, emit } = createOffice({ readOnly: true });
  emit(source);
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  let browser;
  try {
    browser = await chromium.launch({ executablePath: process.env.CHROME_PATH, headless: true,
      args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
    const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });
    const errors = []; page.on('pageerror', error => errors.push(error.message));
    await page.goto(`http://127.0.0.1:${server.address().port}`);
    await page.waitForFunction(() => window.__office?.currentWorld());
    await page.waitForTimeout(1500);
    assert.equal(await page.locator('#sAgents').textContent(), String(source.actors.length));
    assert.match(await page.locator('#worldStatus').textContent(), /Đã dừng/);
    await page.screenshot({ path: path.join(out, 'actual-world.png') });
    const red = source.actors.find(a => a.id === 'red-impact');
    if (source.trace && red) {
      await page.selectOption('#teamFilter', 'red');
      await page.getByRole('button', { name: `Xem hoạt động ${red.id}`, exact: true }).click();
      await page.locator('#inspector').waitFor({ state: 'visible' });
      assert.equal(await page.locator('#inspectorTitle').textContent(), red.id);
      const job = source.trace.events.find(e => e.actor_id === red.id && e.tool === 'register_job');
      assert(job, 'Run the scripted inspector demo with at least 18 ticks');
      await page.locator(`#traceTimeline [data-event-id="${job.id}"]`).click();
      assert.match(await page.locator('#traceEvent').textContent(), /register_job/);
      assert.match(await page.locator('#traceEvent').textContent(), /scripted/);
      assert.match(await page.locator('#traceCases').textContent(), /quarantine/);
      assert.match(await page.locator('#traceCases').textContent(), /Thay đổi đã được xác minh/);
      await page.screenshot({ path: path.join(out, 'red-agent-inspector.png') });
      await page.locator('#traceRelated').uncheck();
      const ownCount = source.trace.events.filter(e => e.actor_id === red.id).length;
      assert.equal(await page.locator('#traceTimeline .trace-row').count(), ownCount);
      await page.keyboard.press('Escape');
      await page.locator('#inspector').waitFor({ state: 'hidden' });
      // Hit the real 3D desk/monitor rather than invoking the selection callback.
      const point = await page.evaluate(id => window.__office.deskScreenPoint(id), `${source.world_id}/${red.id}`);
      assert(point); await page.mouse.click(point.x, point.y);
      await page.locator('#inspector').waitFor({ state: 'visible' });
      assert.equal(await page.locator('#inspectorTitle').textContent(), red.id);
      await page.keyboard.press('Escape');
      // An execution target is untrusted display data, never HTML to execute.
      const hostile = structuredClone(source);
      hostile.world_id = 'ui-test-escaping'; hostile.trace.events.find(e => e.id === job.id).target = '<img src=x onerror="window.__traceXss=1">';
      emit(hostile);
      await page.locator('#worldSelect option[value="ui-test-escaping"]').waitFor({ state: 'attached' });
      await page.selectOption('#worldSelect', 'ui-test-escaping');
      await page.getByRole('button', { name: `Xem hoạt động ${red.id}`, exact: true }).click();
      await page.locator(`#traceTimeline [data-event-id="${job.id}"]`).click();
      assert.match(await page.locator('#traceEvent').textContent(), /<img src=x/);
      assert.equal(await page.locator('#inspector img').count(), 0);
      assert.equal(await page.evaluate(() => window.__traceXss), undefined);
      await page.keyboard.press('Escape');
    }
    // Synthetic 200-agent roster tests pagination; never presented as a measured run.
    const actors = Array.from({ length: 200 }, (_, i) => ({
      ...source.actors[0], id: `test-${i}`, team: i < 90 ? 'client' : i < 150 ? 'red' : 'blue',
      role: 'viewer-test', turns: 10, last_tick: 10, last_tool: 'browse', source: 'scripted',
    }));
    const value = { ...source, trace: null, world_id: 'ui-test-200', actors, tick: 10, status: 'running', updated_at: Date.now() / 1000 };
    emit(value);
    await page.locator('#worldSelect option[value="ui-test-200"]').waitFor({ state: 'attached' });
    await page.selectOption('#worldSelect', 'ui-test-200');
    await page.selectOption('#teamFilter', 'all');
    assert.equal(await page.locator('#cards .card').count(), 20);
    assert.match(await page.locator('#pageInfo').textContent(), /1\/10/);
    await page.click('#nextPage');
    assert.match(await page.locator('#pageInfo').textContent(), /2\/10/);
    await page.selectOption('#teamFilter', 'blue');
    assert.match(await page.locator('#pageInfo').textContent(), /1\/3.*50 agent/);
    assert(await page.evaluate(() => window.__office.agents.every(a => a.worldActor.team === 'blue')));
    await page.click('#nextPage'); await page.click('#nextPage');
    assert.equal(await page.locator('#cards .card').count(), 10);
    assert.equal(await page.locator('#nextPage').isDisabled(), true);
    await page.reload();
    await page.waitForFunction(() => window.__office?.currentWorld());
    await page.selectOption('#worldSelect', 'ui-test-200');
    assert.equal(await page.locator('#sAgents').textContent(), '200');
    // Time advances in the browser only; heartbeat must become stale without a new event.
    await page.evaluate(() => { const now = Date.now(); Date.now = () => now + 120000; });
    await page.waitForFunction(() => document.getElementById('worldStatus').textContent.includes('Mất cập nhật'));
    assert.equal(await page.locator('#sActive').textContent(), '0');
    emit({ ...value, status: 'stopped', updated_at: value.updated_at + 1 });
    await page.waitForFunction(() => document.getElementById('worldStatus').textContent.includes('Đã dừng'));
    emit({ ...value, run_id: 'resumed', updated_at: Date.now() / 1000 + 121 });
    await page.waitForFunction(() => document.getElementById('worldStatus').textContent.includes('Đang chạy'));
    emit({ ...value, run_id: 'resumed', engine: 'hybrid', key_layout: 'teams', budget_exhausted: true,
      llm: { attempts: 7, successes: 5, input_tokens: 100, output_tokens: 25 },
      pools: { red: { model: 'test-model', first_key: 201, last_key: 400, keys: 200, active_key: 202, state: 'cooling_down' } },
      updated_at: Date.now() / 1000 + 122 });
    await page.waitForFunction(() => document.getElementById('sCalls').textContent === '7');
    assert.match(await page.locator('#worldUsage').textContent(), /5\/7.*125 token.*hết ngân sách/);
    assert.match(await page.locator('#teamMetrics').textContent(), /Key #202.*201–400/s);
    assert.match(await page.locator('#teamMetrics').textContent(), /cooling_down/);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.click('#toggleTeam');
    await page.screenshot({ path: path.join(out, 'mobile-roster.png') });
    await page.locator('#cards .card').first().click();
    await page.locator('#inspector').waitFor({ state: 'visible' });
    assert.match(await page.locator('#traceWindow').textContent(), /Snapshot cũ/);
    const box = await page.locator('#inspector').boundingBox();
    assert(box.x >= 0 && box.x + box.width <= 390);
    await page.keyboard.press('Escape');
    if (source.trace && red) {
      await page.selectOption('#worldSelect', source.world_id);
      await page.selectOption('#teamFilter', 'red');
      await page.getByRole('button', { name: `Xem hoạt động ${red.id}`, exact: true }).click();
      await page.locator('#inspector').waitFor({ state: 'visible' });
      await page.screenshot({ path: path.join(out, 'mobile-inspector.png') });
    }
    assert.deepEqual(errors, []);
    const result = { passed: true, actual_world: source.world_id, actual_actors: source.actors.length,
      synthetic_pagination_actors: 200, actual_inspector_checked: !!(source.trace && red),
      checks: ['roster', 'team filter', 'pagination', 'SSE replay', 'stale', 'stopped', 'resume', 'quota indices', 'usage counters', 'budget fallback', 'mobile', 'legacy trace empty state', 'no browser errors'] };
    await fs.writeFile(path.join(out, 'verification.json'), JSON.stringify(result, null, 2));
    console.log(JSON.stringify(result));
  } finally {
    if (browser) await browser.close(); server.closeAllConnections(); await new Promise(r => server.close(r));
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
