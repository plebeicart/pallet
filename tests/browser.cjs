// QA only. Uses a local HTTP server and mocked API; never sends mail.
// PLAYWRIGHT_MODULE=/path/to/playwright node tests/browser.cjs
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs/promises');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const root = path.resolve(__dirname, '..');
const types = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml', '.webp': 'image/webp', '.png': 'image/png', '.jpg': 'image/jpeg', '.ttf': 'font/ttf' };
const server = http.createServer(async (req, res) => {
 try {
  if (req.url === '/api/requests/config') {
   res.setHeader('Content-Type', 'application/json');
   return res.end(JSON.stringify({ enabled: false }));
  }
  const name = new URL(req.url, 'http://localhost').pathname;
  if (!/^\/(?:index\.html|privacy\.html|consent\.html|(?:css|js|assets)\/.*)?$/.test(name)) {
   res.writeHead(404); return res.end();
  }
  const file = path.resolve(root, '.' + (name === '/' ? '/index.html' : name));
  if (!file.startsWith(root + path.sep)) throw Error('Invalid path');
  res.setHeader('Content-Type', types[path.extname(file)] || 'application/octet-stream');
  res.end(await fs.readFile(file));
 } catch { res.writeHead(404); res.end(); }
});

(async () => {
 await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
 const base = `http://127.0.0.1:${server.address().port}`;
 const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/usr/bin/chromium', headless: true });
 let checks = 0;
 const check = condition => { assert(condition); checks++; };
 try {
  // Native submission must stay blocked with JS disabled OR its file unavailable.
  for (const scenario of ['no-js', 'blocked-js']) {
   const context = await browser.newContext({ javaScriptEnabled: scenario !== 'no-js', reducedMotion: 'reduce' });
   const safePage = await context.newPage();
   if (scenario === 'blocked-js') await safePage.route('**/js/main.js', route => route.abort());
   await safePage.goto(base);
   const submissions = [];
   safePage.on('request', req => { if (req.isNavigationRequest() || req.method() === 'POST') submissions.push(req.url()); });
   for (const form of await safePage.locator('[data-lead]').all()) {
    check(await form.getAttribute('method') === 'post');
    check(await form.locator('[type=submit]').isDisabled());
   }
   const form = safePage.locator('[data-form=main]');
   await form.locator('[name=name]').fill('Audit Test');
   await form.locator('[name=phone]').fill('79990000000');
   await form.locator('[name=consent]').check();
   await form.locator('[name=phone]').press('Enter');
   // Exercise the cancellation fallback even if controls are forced enabled.
   if (scenario === 'blocked-js') await safePage.locator('[data-lead]').evaluateAll(forms => forms.forEach(f => { f.elements.name.value = 'Audit Test'; f.elements.phone.value = '79990000000'; f.elements.consent.checked = true; f.querySelector('[type=submit]').disabled = false; f.requestSubmit(); }));
   await safePage.waitForTimeout(100);
   check(submissions.length === 0);
   check(!safePage.url().includes('phone='));
   await context.close();
  }
  const page = await browser.newPage({ reducedMotion: 'reduce' });
  const errors = [];
  page.on('pageerror', err => errors.push(err.message));
  let posts = [];
  let mode = 'error';
  let release;
  let gate;
  await page.route('**/api/requests', async route => {
   posts.push(route.request().postDataJSON());
   if (mode === 'pending') await gate;
   if (mode === 'network') return route.abort('failed');
   if (mode === 'invalid-json') return route.fulfill({ status: 200, body: 'bad' });
   const status = mode === 'error' ? 502 : mode === 'rate' ? 429 : mode === 'disabled' ? 503 : 200;
   await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify({ ok: status === 200 }) });
  });
  const fill = async form => {
   await form.locator('[name=name]').fill('Иван');
   await form.locator('[name=phone]').fill('+7 (999) 117-88-28');
   await form.locator('[name=consent]').check();
  };
  await page.goto(base);
  await page.waitForFunction(() => document.querySelector('[data-form=main] button').textContent.includes('Проверить'));
  const main = page.locator('[data-form=main]');
  const modal = page.locator('[data-form=modal]');
  await fill(main);
  await main.locator('[type=submit]').click();
  check((await main.locator('.form-status').innerText()).includes('не отправлена'));
  check(posts.length === 0);
  check(await page.locator('[data-lead]').count() === 2);
  for (const width of [320, 375, 768, 1440, 1920, 2560]) {
   await page.setViewportSize({ width, height: 1000 });
   check(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  }
  await page.setViewportSize({ width: 375, height: 900 });
  await page.locator('.menu-toggle').click();
  check(await page.locator('.menu-toggle').getAttribute('aria-expanded') === 'true');
  await page.locator('#navigation a').first().click();
  check(await page.locator('.menu-toggle').getAttribute('aria-expanded') === 'false');
  for (const button of await page.locator('[data-filter]').all()) {
   await button.click();
   const filter = await button.getAttribute('data-filter');
   check(await page.locator('.product:visible').count() === await page.locator(filter === 'all' ? '.product' : `.product[data-category~="${filter}"]`).count());
  }
  await page.locator('[data-filter=all]').click();
  await page.setViewportSize({ width: 1440, height: 1000 });
  // Every request/service button must open the shared modal and select its subject.
  for (const button of await page.locator('[data-request], [data-service]').all()) {
   await button.click();
   check(await page.locator('#request-dialog').evaluate(el => el.open));
   check((await modal.locator('[name=subject]').inputValue()).length > 0);
   await page.keyboard.press('Escape');
  }
  for (const name of ['privacy.html', 'consent.html']) {
   check((await page.request.get(`${base}/${name}`)).status() === 200);
  }
  check(await page.locator('img').evaluateAll(imgs => imgs.every(img => img.complete && img.naturalWidth > 0)));
  await page.route('**/api/requests/config', route => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ enabled: true, token: 'test-token' }) }));
  await page.reload();
  await page.waitForFunction(() => document.querySelector('[data-form=main] button').textContent.includes('Отправить'));
  check(await page.locator('.demo-notice:visible').count() === 0);
  await fill(main);
  await main.locator('[name=phone]').fill('123');
  await main.locator('[type=submit]').click();
  check(posts.length === 0);
  await main.locator('[name=phone]').fill('+7 (999) 117-88-28');
  await main.locator('[name=consent]').uncheck();
  await main.locator('[type=submit]').click();
  check(posts.length === 0);
  await main.locator('[name=consent]').check();
  await main.locator('[name=message]').fill('100 штук');
  for (const failure of ['error', 'rate', 'disabled', 'network', 'invalid-json']) {
   mode = failure;
   await main.locator('[type=submit]').click();
   await main.locator('[type=submit]').waitFor({ state: 'visible' });
   await page.waitForFunction(() => !document.querySelector('[data-form=main] button').disabled);
   check(await main.locator('[name=name]').inputValue() === 'Иван');
   check(await main.locator('[name=message]').inputValue() === '100 штук');
   check(!(await main.locator('.form-status').innerText()).includes('Заявка отправлена.'));
  }
  check(new Set(posts.map(p => p.request_id)).size === 1);
  mode = 'pending';
  gate = new Promise(resolve => { release = resolve; });
  const before = posts.length;
  await main.locator('[type=submit]').click();
  await page.waitForFunction(() => document.querySelector('[data-form=main] button').disabled);
  await main.evaluate(el => { el.dispatchEvent(new Event('submit', { cancelable: true })); });
  await page.waitForTimeout(100);
  check(posts.length === before + 1);
  check(await main.getAttribute('aria-busy') === 'true');
  release();
  await page.waitForFunction(() => !document.querySelector('[data-form=main] button').disabled);
  check((await main.locator('.form-status').innerText()).includes('Заявка отправлена.'));
  check(await main.locator('[name=name]').inputValue() === '');
  check(posts[0].form === 'main' && posts[0].message === '100 штук' && posts[0].consent === 'on');
  const product = page.locator('.product [data-request]').first();
  await product.click();
  const subject = await product.getAttribute('data-request');
  await fill(modal);
  mode = 'error';
  await modal.locator('[type=submit]').click();
  await page.waitForFunction(() => !document.querySelector('[data-form=modal] button').disabled);
  await page.keyboard.press('Escape');
  await product.click();
  check(await modal.locator('[name=name]').inputValue() === 'Иван');
  mode = 'success';
  await modal.locator('[type=submit]').click();
  await page.waitForFunction(() => !document.querySelector('[data-form=modal] button').disabled);
  check(posts.at(-1).subject === subject && posts.at(-1).form === 'modal');
  check(posts.at(-1).request_id === posts.at(-2).request_id);
  check((await modal.locator('.form-status').innerText()).includes('Заявка отправлена.'));
  check(await modal.locator('[name=subject]').inputValue() === subject);
  check(errors.length === 0);
  console.log(`${checks} browser assertions passed; 6 viewport widths; no JavaScript errors; SMTP never used.`);
 } finally {
  await browser.close();
  await new Promise(resolve => server.close(resolve));
 }
})().catch(err => { console.error(err); server.close(); process.exitCode = 1; });
