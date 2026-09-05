const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');

test('dashboard authenticates in headers without persisting the token', async () => {
  const browser = await chromium.launch({ headless: true,
    ...(process.env.BROWSER_CHANNEL ? { channel: process.env.BROWSER_CHANNEL } : {}),
  });
  try {
    const page = await browser.newPage();
    const token = 'test-only-' + 'x'.repeat(32);
    const html = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');
    const requests = [];
    let rejectProfile = false;
    await page.route('**/*', async route => {
      const request = route.request();
      const url = new URL(request.url());
      if (url.hostname === 'cdnjs.cloudflare.com') return route.fulfill({ body: '' });
      if (url.pathname === '/') return route.fulfill({ contentType: 'text/html', body: html });
      requests.push(request.url());
      assert.equal(request.url().includes(token), false);
      if (request.headers().authorization !== `Bearer ${token}` || (rejectProfile && url.pathname.includes('/profiles/'))) {
        return route.fulfill({ status: 401, json: { detail: 'Authentication required' } });
      }
      if (url.pathname === '/api/printers') return route.fulfill({ json: [{ id: 1, name: 'Printer' }] });
      if (url.pathname === '/api/materials') return route.fulfill({ json: [{ id: 2, brand: 'Test', material_type: 'PLA' }] });
      if (url.pathname.includes('/profiles/')) return route.fulfill({ status: 404, json: { detail: 'no active profile' } });
      return route.fulfill({ json: [] });
    });
    await page.goto('http://printopt.test/');
    assert.equal(requests.length, 0);
    await page.locator('#apiToken').fill('wrong');
    await page.locator('#connectBtn').click();
    await page.waitForFunction(() => document.querySelector('#connectionStatus').textContent.includes('Invalid API token'));
    await page.locator('#apiToken').fill(token);
    await page.locator('#connectBtn').click();
    await page.waitForFunction(() => document.querySelector('#connectionStatus').textContent === 'Connected.');
    assert.equal(await page.locator('#apiToken').inputValue(), '');
    assert.deepEqual(await page.evaluate(() => [localStorage.length, sessionStorage.length]), [0, 0]);
    await page.locator('#loadBtn').click();
    await page.waitForFunction(() => document.querySelector('#profile').textContent === 'No active profile yet.');
    rejectProfile = true;
    await page.locator('#loadBtn').click();
    await page.waitForFunction(() => document.querySelector('#connectionStatus').textContent.includes('Invalid API token'));
    await page.reload();
    assert.equal(await page.locator('#apiToken').inputValue(), '');
  } finally { await browser.close(); }
});
