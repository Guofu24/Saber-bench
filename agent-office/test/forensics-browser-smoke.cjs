// node test/forensics-browser-smoke.cjs WORLD_OFFICE_JSON OUTPUT_DIR
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
    const errors = []; page.on('pageerror', e => errors.push(e.message));
    await page.goto(`http://127.0.0.1:${server.address().port}`);
    await page.waitForFunction(() => window.__office?.currentWorld());
    await page.selectOption('#teamFilter', 'blue');
    await page.getByRole('button', { name: 'Xem hoạt động blue-dfir', exact: true }).click();
    const query = source.trace.events.find(e => e.tool === 'forensic_query');
    assert(query?.forensics?.evidence?.length);
    await page.locator(`#traceTimeline [data-event-id="${query.id}"]`).click();
    assert.match(await page.locator('.forensic-detail').textContent(), /\/portal/);
    assert.match(await page.locator('.forensic-detail').textContent(), new RegExp(query.forensics.evidence[0].sha256));
    await page.screenshot({ path: path.join(out, 'forensic-query.png') });
    const review = source.trace.events.find(e => e.tool === 'response_review');
    await page.locator(`#traceTimeline [data-event-id="${review.id}"]`).click();
    assert.match(await page.locator('.forensic-detail').textContent(), /containment/);
    await page.screenshot({ path: path.join(out, 'response-gaps.png') });
    const hostile = structuredClone(source);
    hostile.world_id = 'forensic-escaping-test';
    hostile.trace.events.find(e => e.id === query.id).forensics.summary = '<img src=x onerror="window.__forensicXss=1">';
    emit(hostile);
    await page.locator('#worldSelect option[value="forensic-escaping-test"]').waitFor({ state: 'attached' });
    await page.selectOption('#worldSelect', hostile.world_id);
    await page.getByRole('button', { name: 'Xem hoạt động blue-dfir', exact: true }).click();
    await page.locator(`#traceTimeline [data-event-id="${query.id}"]`).click();
    assert.equal(await page.locator('.forensic-detail img').count(), 0);
    assert.equal(await page.evaluate(() => window.__forensicXss), undefined);
    assert.deepEqual(errors, []);
    const receipt = { passed: true, world_id: source.world_id, checks: ['query filters', 'citation hash', 'response gaps', 'HTML escaping', 'no browser errors'] };
    await fs.writeFile(path.join(out, 'verification.json'), JSON.stringify(receipt, null, 2));
    console.log(JSON.stringify(receipt));
  } finally {
    if (browser) await browser.close();
    server.closeAllConnections(); await new Promise(resolve => server.close(resolve));
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
