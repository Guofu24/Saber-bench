// Run against public exports produced by actual loopback or target lab executors.
const fs = require('node:fs/promises');
const path = require('node:path');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright-core');
const { createOffice } = require('../lib/server');
const { snapshotSource } = require('../lib/watch');

async function main() {
  const read = await snapshotSource({ world: process.argv[2] });
  const source = await read();
  assert.equal(source.execution_mode, 'range');
  assert.equal(source.status, 'stopped', 'Stop the fixture before checking its immutable UI evidence');
  const out = path.resolve(process.argv[3]); await fs.mkdir(out, { recursive: true });
  let guidanceExport = null;
  const { server, emit } = createOffice({ readOnly: true,
    readRange: actor => guidanceExport?.actor_id === actor ? guidanceExport : read.range(actor) });
  emit(source); await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  let browser;
  try {
    browser = await chromium.launch({ executablePath: process.env.CHROME_PATH, headless: true,
      args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const errors = []; page.on('pageerror', e => errors.push(e.message));
    await page.goto(`http://127.0.0.1:${server.address().port}`);
    await page.waitForFunction(() => window.__office?.currentWorld());
    for (const team of ['client', 'red', 'blue']) {
      const actor = source.actors.find(a => a.team === team && a.turns > 0);
      assert.ok(actor);
      await page.selectOption('#teamFilter', team);
      await page.getByRole('button', { name: `Xem hoạt động ${actor.id}`, exact: true }).click();
      await page.locator('#nativeAll').check();
      await page.locator('#nativeEvents .range-job').first().waitFor();
      assert.match(await page.locator('#nativeHistoryLabel').textContent(), /12 job/);
      const evidence = await read.range(actor.id);
      assert.equal(await page.locator('#nativeEvents .range-job').count(), evidence.entries.length);
      const job = page.locator('#nativeEvents .range-job').first();
      await job.locator(':scope > summary').click();
      assert.match(await job.textContent(), /process.launch/);
      assert.match(await job.textContent(), /process.exit/);
      assert.match(await job.textContent(), /pid/);
      assert.match(await job.textContent(), /Hash bản gốc/);
      if (team === 'client') {
        const screen = page.locator('.range-screen');
        await screen.locator('summary').click();
        await page.waitForFunction(() => document.querySelector('.range-screen img')?.naturalWidth > 0);
        assert.equal(await screen.locator('img').getAttribute('src'), 'data:image/png;base64,' + evidence.screen.png);
      }
      await page.locator('#nativeEvents').scrollIntoViewIfNeeded();
      await page.screenshot({ path: path.join(out, `${team}-range.png`) });
      await page.locator('#nativeAll').uncheck();
      await page.waitForFunction(() => document.querySelectorAll('.range-job').length === 1);
      await page.keyboard.press('Escape');
    }
    // Explicit display fixtures: a controller lookup must not claim process evidence,
    // including old exports that incorrectly set evidence_complete for guidance.
    const client = source.actors.find(a => a.team === 'client' && a.turns > 0);
    for (const status of [200, 404]) {
      const fixture = structuredClone(source);
      fixture.world_id = `guidance-display-fixture-${status}`;
      const actor = fixture.actors.find(a => a.id === client.id);
      const event = [...fixture.trace.events].reverse().find(e => e.actor_id === actor.id);
      event.tool = 'consult_skill'; event.target = 'controller'; event.status = status;
      actor.last_tool = event.tool; actor.last_status = status;
      actor.executor = { host: 'controller', job_id: require('node:crypto').randomUUID(), artifacts: [] };
      guidanceExport = { schema_version: 1, world_id: fixture.world_id, actor_id: actor.id,
        through_tick: fixture.tick, limit: 12, screen: null, entries: [{
          job_id: actor.executor.job_id, tick: event.tick, event_id: event.id,
          tool: event.tool, source: 'scripted', evidence: [], artifacts: [], evidence_complete: true,
          result: { status, guidance_only: true, executor_host: 'controller' },
        }] };
      emit(fixture);
      await page.locator(`#worldSelect option[value="${fixture.world_id}"]`).waitFor({ state: 'attached' });
      await page.selectOption('#worldSelect', fixture.world_id);
      await page.selectOption('#teamFilter', 'client');
      await page.getByRole('button', { name: `Xem hoạt động ${actor.id}`, exact: true }).click();
      const job = page.locator('#nativeEvents .range-job').first();
      await job.waitFor();
      assert.match(await job.textContent(), /Tra cứu hướng dẫn tại controller/);
      assert.doesNotMatch(await job.textContent(), /Đã nhận và kiểm hash|process.launch|process.exit/);
      assert.match(await page.locator('#traceEvent').textContent(), /không tự thực hiện/);
      await page.screenshot({ path: path.join(out, `guidance-${status}.png`) });
      await page.keyboard.press('Escape');
    }
    assert.deepEqual(errors, []);
    const result = { passed: true, world_id: source.world_id,
      checks: ['three-team actual process evidence', 'per-job filter', 'verified real browser image',
        'guidance display fixtures never claim remote execution', 'no browser errors'],
      scope: 'loopback executor and viewer acceptance; no Docker, AD, Zeek or Sysmon claim' };
    await fs.writeFile(path.join(out, 'verification.json'), JSON.stringify(result, null, 2));
    console.log(JSON.stringify(result));
  } finally {
    if (browser) await browser.close(); server.closeAllConnections(); await new Promise(r => server.close(r));
  }
}
main().catch(e => { console.error(e); process.exitCode = 1; });
