const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');

test('API strings stay text and run selection still loads measurements', async () => {
  const browser = await chromium.launch({
    headless: true,
    ...(process.env.BROWSER_CHANNEL ? { channel: process.env.BROWSER_CHANNEL } : {}),
  });
  try {
    const page = await browser.newPage();
    const payloads = ['<img src=x onerror="window.injected=1">', '</td><svg onload="window.injected=2">', 'Flow & "quoted" café'];
    const html = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');
    let resultLoads = 0;
    await page.route('**/*', async route => {
      const url = new URL(route.request().url());
      if (url.hostname === 'cdnjs.cloudflare.com') {
        return route.fulfill({ contentType: 'application/javascript', body: 'window.Chart = class { constructor(ctx, config) { window.lastChart = config; } destroy() {} };' });
      }
      if (url.pathname === '/') return route.fulfill({ contentType: 'text/html', body: html });
      let data;
      if (url.pathname === '/api/printers') data = [{ id: 1, name: payloads[0] }];
      else if (url.pathname === '/api/materials') data = [{ id: 2, brand: payloads[1], material_type: 'PLA' }];
      else if (url.pathname.startsWith('/api/profiles/')) data = { params: { flow_ratio: 1.02 } };
      else if (url.pathname === '/api/test_runs') data = payloads.map((test_type, i) => ({ id: i + 3, test_type, status: 'pending', created_at: '2026-09-05' }));
      else if (url.pathname.endsWith('/results')) { resultLoads++; data = [{ param_value: 1, measured_value: 0.4 }]; }
      else return route.abort();
      return route.fulfill({ json: data });
    });
    await page.goto('http://printopt.test/');
    // Also runs when combined with the independently reviewed auth change.
    if (await page.locator('#connectBtn').count()) {
      await page.locator('#apiToken').fill('test-only-' + 'x'.repeat(32));
      await page.locator('#connectBtn').click();
    }
    await page.waitForFunction(() => document.querySelector('#material option'));
    assert.equal(await page.locator('#printer option').textContent(), payloads[0]);
    assert.equal(await page.locator('#material option').textContent(), `${payloads[1]} PLA`);
    assert.equal(await page.locator('#printer').inputValue(), '1');
    await page.locator('#loadBtn').click();
    await page.waitForFunction(() => document.querySelectorAll('#runsTable tbody tr').length === 3);
    assert.deepEqual(await page.locator('#runsTable tbody tr td:nth-child(2)').allTextContents(), payloads);
    assert.equal(await page.locator('img, svg').count(), 0);
    assert.equal(await page.evaluate(() => window.injected), undefined);
    await page.locator('#runsTable tbody tr').first().click();
    await page.waitForFunction(() => window.lastChart);
    assert.equal(resultLoads, 1);
    assert.deepEqual(await page.evaluate(() => window.lastChart.data.datasets[0].data), [{ x: 1, y: 0.4 }]);
    await page.locator('#loadBtn').click();
    assert.equal(await page.locator('#runsTable tbody tr').count(), 3);
  } finally {
    await browser.close();
  }
});
