// Run against the isolated file_storage_smoke_server fixture, never production.
const { chromium, expect } = require('@playwright/test');
const fs = require('fs');
(async () => {
  const browser = await chromium.launch({ headless: true, channel: 'chromium', args: ['--no-sandbox'] });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, acceptDownloads: true });
  await context.addInitScript(() => { if (window === window.top && location.origin === 'http://127.0.0.1:5187') window.localStorage?.setItem('nexgent.language', 'en'); });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  try {
    await page.goto('http://127.0.0.1:5187/file-storage');
    await page.getByLabel('Username', {exact:true}).fill('alice');
    await page.getByLabel('Password', {exact:true}).fill('test-pass');
    await page.getByRole('button', {name:'Sign in', exact:true}).click();
    await expect(page.getByRole('heading', {name:'File Storage', exact:true})).toBeVisible();
    expect(await page.evaluate(async () => (await (await fetch('/api/file-storage-test-fixture')).json()).fixture)).toBe('isolated-file-storage-smoke');
    const open = async name => {
      await page.getByRole('button', {name, exact:true}).click();
      await expect(page.getByRole('heading', {name, exact:true})).toBeVisible();
    };
    const back = () => page.getByRole('button', {name:'Back to files', exact:true}).click();
    await open('Meeting notes.md');
    await expect(page.getByRole('heading', {name:'Meeting', exact:true})).toBeVisible();
    await back();
    await open('Preview image.png');
    await expect(page.getByRole('img', {name:'Preview image.png'})).toBeVisible();
    await expect.poll(() => page.getByRole('img', {name:'Preview image.png'}).evaluate(img => img.naturalWidth)).toBeGreaterThan(0);
    await page.screenshot({path:'/tmp/file-storage-preview-image.png',fullPage:true});
    await back();
    for (const name of ['Preview document.pdf', 'Preview document.docx', 'Preview budget.xlsx']) {
      await open(name);
      const frame = page.locator(`iframe[title="${name}"]`);
      await expect(frame).toHaveAttribute('src', /^blob:/, {timeout:60000});
      const bytes = await frame.evaluate(async el => Array.from(new Uint8Array(await (await fetch(el.src)).arrayBuffer())).slice(0,5));
      expect(Buffer.from(bytes).toString()).toBe('%PDF-');
      if (name.endsWith('xlsx')) {
        const event = page.waitForEvent('download');
        await page.getByRole('button', {name:'Download', exact:true}).click();
        const downloaded = await event;
        expect(downloaded.suggestedFilename()).toBe(name);
        expect(fs.readFileSync(await downloaded.path()).subarray(0,2).toString()).toBe('PK');
        await page.setViewportSize({width:760,height:900});
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        await expect.poll(() => page.frames().some(frame => frame.url().startsWith('chrome-extension://')), {timeout:15000}).toBe(true);
        await page.screenshot({path:'/tmp/file-storage-preview-excel.png',fullPage:true});
      }
      await back();
    }
    // Simulate unsupported and transient conversion failures through the actual UI.
    await page.route('**/api/file-storage/entries/*/preview', route => route.fulfill({status:415,contentType:'application/json',body:JSON.stringify({error:{code:'preview_unsupported'}})}));
    await open('Meeting notes.md');
    await expect(page.getByRole('heading', {name:'Preview unavailable',exact:true})).toBeVisible();
    await expect(page.getByRole('button', {name:'Download',exact:true})).toBeEnabled();
    await expect(page.getByRole('button', {name:'Try again',exact:true})).toHaveCount(0);
    await back();
    await page.unroute('**/api/file-storage/entries/*/preview');
    await page.route('**/api/file-storage/entries/*/preview', route => route.fulfill({status:504,contentType:'application/json',body:JSON.stringify({error:{code:'preview_timeout'}})}));
    await open('Meeting notes.md');
    await expect(page.getByRole('button', {name:'Try again',exact:true})).toBeVisible();
    await page.unroute('**/api/file-storage/entries/*/preview');
    await page.getByRole('button', {name:'Try again',exact:true}).click();
    await expect(page.getByRole('heading', {name:'Meeting',exact:true})).toBeVisible();
    await page.getByRole('button', {name:'File details',exact:true}).click();
    await expect(page.getByRole('dialog')).toBeVisible();
    await page.getByRole('button', {name:'Open containing folder',exact:true}).click();
    await expect(page.getByRole('heading', {name:'File Storage',exact:true})).toBeVisible();
    expect(errors).toEqual([]);
    console.log('PASS: Markdown, image, PDF, real Word/Excel conversion, original download, narrow viewer, unsupported fallback, conversion retry, details and return navigation.');
  } catch(e) { await page.screenshot({path:'/tmp/file-storage-preview-failure.png',fullPage:true}); throw e; }
  finally { await browser.close(); }
})().catch(e => { console.error(e); process.exit(1); });
