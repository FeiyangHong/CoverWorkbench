// Invoked by capture_readme.py; never connect this to a personal workspace.
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const path = require('node:path');

(async () => {
  const browser = await chromium.launch({headless: true,
    ...(process.env.CW_BROWSER_CHANNEL ? {channel: process.env.CW_BROWSER_CHANNEL} : {})});
  try {
    const page = await browser.newPage({viewport: {width: 1440, height: 960}, deviceScaleFactor: 1});
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(process.argv[2]);
    await page.locator('#title').filter({hasText: 'Moonlit Demo'}).waitFor();
    await page.locator('#nativeInventory').filter({hasText: '尚未保存'}).waitFor({state: 'attached'});
    await page.screenshot({path: path.join(process.argv[3], 'workflow.png')});
    await page.locator('[data-tab=daw]').click();
    await page.locator('#dawRecipe').filter({hasText: 'Pro-Q 3'}).waitFor();
    await page.locator('#dawInspect').click();
    await page.locator('.daw-track').last().waitFor();
    assert.equal(await page.locator('.daw-track').count(), 3);
    // Display-only path normalization: no backend results, roles or plugin state are invented.
    await page.locator('#dawSVP').evaluate(input => {input.value = 'C:\\CoverWorkbench\\projects\\demo\\working\\sv\\project.svp';});
    await page.locator('#dawName').fill('Moonlit Demo');
    await page.locator('#dawOutputDir').fill('C:\\CoverWorkbench\\projects\\studio-one');
    await page.evaluate(() => {document.activeElement.blur(); window.scrollTo(0, 0);});
    const cards = await Promise.all([page.locator('#daw .work-card').first().boundingBox(), page.locator('#dawRecipe').locator('..').boundingBox()]);
    await page.setViewportSize({width: 1440, height: Math.ceil(Math.max(...cards.map(card => card.y + card.height)) + 18)});
    await page.screenshot({path: path.join(process.argv[3], 'studio-one.png')});
    assert.deepEqual(errors, []);
    console.log('Captured two isolated demo screens; no native rendering or Song generation performed.');
  } finally {
    await browser.close();
  }
})().catch(error => {console.error(error); process.exit(1);});
