// Actual workload UI smoke; reuse an existing external Playwright install.
const fs = require('node:fs/promises');
const path = require('node:path');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright-core');
const { createOffice } = require('../lib/server');
const { snapshotSource } = require('../lib/watch');

async function main() {
  const read = await snapshotSource({ world: process.argv[2] });
  const source = await read();
  const out = path.resolve(process.argv[3]); await fs.mkdir(out, { recursive: true });
  const { server, emit } = createOffice({ readOnly: true, readNative: read.native });
  emit(source);
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
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
      await page.selectOption('#teamFilter', team);
      await page.getByRole('button', { name: `Xem hoạt động ${actor.id}`, exact: true }).click();
      await page.locator('#nativeEvents .native-row').first().waitFor();
      const evidence = await read.native(actor.id);
      assert.equal(await page.locator('#nativeEvents .native-row').count(), evidence.events.length);
      assert.match(await page.locator('#nativeScope').textContent(), /chưa giám sát toàn hệ điều hành/);
      assert.match(await page.locator('#nativeEvents').textContent(), /dns.response/);
      assert.match(await page.locator('#nativeEvents').textContent(), /network.connect/);
      assert.match(await page.locator('#nativeEvents').textContent(), /file.read/);
      await page.locator('#nativeAll').uncheck();
      await page.waitForFunction(() => document.querySelectorAll('#nativeEvents .native-row').length === 7);
      const process = page.locator('#nativeEvents .native-row').filter({ hasText: 'process.start' });
      await process.locator('summary').click();
      assert.match(await process.textContent(), /native_worker.py/);
      await page.locator('#nativeScope').scrollIntoViewIfNeeded();
      await page.screenshot({ path: path.join(out, `${team}-native.png`) });
      await page.locator('#nativeAll').check();
      await page.keyboard.press('Escape');
    }
    assert.deepEqual(errors, []);
    const result = { passed: true, world_id: source.world_id, actual_actors: source.actors.length,
      checks: ['actual client/red/blue native pages', 'per-actor history', 'application event filter',
        'PID and command line', 'file and DNS/TCP evidence', 'coverage disclaimer', 'no browser errors'] };
    await fs.writeFile(path.join(out, 'verification.json'), JSON.stringify(result, null, 2));
    console.log(JSON.stringify(result));
  } finally {
    if (browser) await browser.close(); server.closeAllConnections(); await new Promise(r => server.close(r));
  }
}
main().catch(e => { console.error(e); process.exitCode = 1; });
