// Browser regression for tests/file_storage_smoke_server.py only.
// Requires @playwright/test and headless Chromium (install in /tmp; see docs).
// Start the isolated backend on 8769 and frontend on 5187 before running.
const { chromium, expect } = require('@playwright/test');
(async () => {
  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, acceptDownloads: true });
  await context.addInitScript(() => localStorage.setItem('nexgent.language', 'en'));
  const page = await context.newPage();
  const failures = [];
  page.on('pageerror', error => failures.push(error.message));
  try {
    await page.goto('http://127.0.0.1:5187/file-storage');
    await page.getByLabel('Username', { exact: true }).fill('alice');
    await page.getByLabel('Password', { exact: true }).fill('test-pass');
    await page.getByRole('button', { name: 'Sign in', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'File Storage', exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Projects', exact: true })).toBeVisible();
    await page.evaluate(async () => {
      const marker = await (await fetch('/api/file-storage-test-fixture')).json();
      if (marker.fixture !== 'isolated-file-storage-smoke') throw new Error('Requires the isolated storage fixture');
      const me = await (await fetch('/api/me')).json();
      for (const name of ['Projects(1)', 'duplicate.txt', 'duplicate(1).txt', 'duplicate(2).txt', 'Design assets', 'Design handoff', 'Copy draft.txt', 'ui-notes.txt', '업로드.txt', 'retry-upload.txt', 'Recovered budget.csv']) {
        const listing = await (await fetch('/api/file-storage/entries?q=' + encodeURIComponent(name))).json();
        for (const item of listing.items.filter(item => item.name === name)) {
          await fetch('/api/file-storage/entries/' + item.id, {method:'DELETE',headers:{'X-CSRF-Token':me.csrf_token}});
        }
      }
      const copies = await (await fetch('/api/file-storage/entries?q=Brand')).json();
      for (const item of copies.items.filter(item => item.parent_id)) await fetch('/api/file-storage/entries/' + item.id, {method:'DELETE',headers:{'X-CSRF-Token':me.csrf_token}});
      const trash = await (await fetch('/api/file-storage/trash')).json();
      for (const item of trash.items) await fetch('/api/file-storage/trash/' + item.id, {method:'DELETE',headers:{'X-CSRF-Token':me.csrf_token}});
    });
    await page.getByRole('button', { name: 'Refresh files', exact: true }).click();
    await expect(page.getByRole('button', { name: 'Design handoff', exact: true })).toHaveCount(0);
    await page.screenshot({ path: '/tmp/file-storage-desktop.png', fullPage: true });
    const dialog = page.getByRole('dialog');
    const menu = async name => page.getByRole('button', { name: `Actions for ${name}`, exact: true }).click();
    const createFolder = async name => {
      await page.getByRole('button', { name: 'New folder', exact: true }).click();
      await dialog.getByLabel('Name', { exact: true }).fill(name);
      await dialog.getByRole('button', { name: 'New folder', exact: true }).click();
      await expect(dialog).not.toBeVisible();
    };
    await createFolder('Design assets');
    await menu('Design assets'); await page.getByRole('button', { name: 'Rename', exact: true }).click();
    await dialog.getByLabel('Name', { exact: true }).fill('Design handoff');
    await dialog.getByRole('button', { name: 'Rename', exact: true }).click();
    await expect(dialog).not.toBeVisible();
    await page.getByRole('button', { name: 'Design handoff', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'This folder is empty' })).toBeVisible();
    const nestedURL = page.url();
    await page.reload(); await expect(page.getByRole('heading', { name: 'This folder is empty' })).toBeVisible();
    await page.goBack(); await expect(page.getByRole('button', { name: 'Projects', exact: true })).toBeVisible();
    await page.goForward(); await expect(page).toHaveURL(nestedURL);
    await page.getByRole('navigation', { name: 'Current folder' }).getByRole('button', { name: 'My files', exact: true }).click();
    await page.getByLabel('Choose files to upload', { exact: true }).setInputFiles([
      { name: 'ui-notes.txt', mimeType: 'text/plain', buffer: Buffer.from('browser integration bytes') },
      { name: '업로드.txt', mimeType: 'text/plain', buffer: Buffer.from('Korean filename') }
    ]);
    await expect(dialog.getByText("Duplicate names get a number automatically, for example file(1).pdf. Existing files are never overwritten.")).toBeVisible();
    await dialog.getByRole('button', { name: 'Upload files', exact: true }).click();
    await expect(dialog).not.toBeVisible(); await expect(page.getByRole('button', { name: 'ui-notes.txt', exact: true })).toBeVisible();
    await menu('업로드.txt');
    const downloadEvent = page.waitForEvent('download');
    await page.getByRole('button', { name: 'Download', exact: true }).click();
    const downloaded = await downloadEvent; expect(downloaded.suggestedFilename()).toBe('업로드.txt');
    const fs = require('fs'); expect(fs.readFileSync(await downloaded.path(), 'utf8')).toBe('Korean filename');
    await menu('ui-notes.txt'); await page.getByRole('button', { name: 'Move to', exact: true }).click();
    await dialog.getByRole('button', { name: 'Projects', exact: true }).click();
    await dialog.getByRole('button', { name: 'Move to', exact: true }).click();
    await expect(dialog).not.toBeVisible(); await expect(page.getByRole('button', { name: 'ui-notes.txt', exact: true })).toHaveCount(0);
    await page.getByRole('button', { name: 'Projects', exact: true }).click();
    await menu('ui-notes.txt'); await page.getByRole('button', { name: 'Copy to', exact: true }).click();
    await dialog.getByLabel('Name', { exact: true }).fill('Copy draft.txt');
    await dialog.getByRole('button', { name: 'Copy to', exact: true }).click();
    await expect(dialog).not.toBeVisible();
    await page.getByRole('navigation', { name: 'Current folder' }).getByRole('button', { name: 'My files', exact: true }).click();
    await expect(page.getByRole('button', { name: 'Copy draft.txt', exact: true })).toBeVisible();
    await page.getByLabel('Search all files', { exact: true }).fill('ui-notes'); await page.getByRole('button', { name: 'Search', exact: true }).click();
    await page.getByRole('button', { name: 'ui-notes.txt', exact: true }).click();
    await page.getByRole('button', { name: 'File details', exact: true }).click();
    await expect(dialog.getByText('My files / Projects', { exact: true })).toBeVisible();
    await dialog.getByRole('button', { name: 'Open containing folder', exact: true }).click();
    await expect(page.getByRole('navigation', { name: 'Current folder' }).getByRole('button', { name: 'Projects' })).toBeVisible();
    await page.getByRole('navigation', { name: 'Current folder' }).getByRole('button', { name: 'My files', exact: true }).click();
    await menu('Copy draft.txt'); await page.getByRole('button', { name: 'Move to trash', exact: true }).click();
    await dialog.getByRole('button', { name: 'Cancel', exact: true }).click();
    await expect(page.getByRole('button', { name: 'Copy draft.txt', exact: true })).toBeVisible();
    await menu('Copy draft.txt'); await page.getByRole('button', { name: 'Move to trash', exact: true }).click();
    await dialog.getByRole('button', { name: 'Move to trash', exact: true }).click();
    await expect(dialog).not.toBeVisible();
    await page.getByRole('button', { name: 'Trash', exact: true }).click();
    await menu('Copy draft.txt'); await page.getByRole('button', { name: 'Restore', exact: true }).click();
    await dialog.getByRole('button', { name: 'Restore', exact: true }).click();
    await expect(dialog).not.toBeVisible(); await expect(page.getByRole('heading', { name: 'Trash is empty' })).toBeVisible();
    await page.getByRole('button', { name: 'My files', exact: true }).click();
    await page.getByRole('checkbox', { name: 'Select Copy draft.txt', exact: true }).check();
    await page.getByRole('checkbox', { name: 'Select 업로드.txt', exact: true }).check();
    await page.getByRole('group', { name: 'Selected file actions' }).getByRole('button', { name: 'Move to trash', exact: true }).click();
    await dialog.getByRole('button', { name: 'Move to trash', exact: true }).click();
    await expect(dialog).not.toBeVisible();
    await page.getByRole('button', { name: 'Trash', exact: true }).click();
    await page.getByRole('checkbox', { name: 'Select all items on this page', exact: true }).check();
    await page.getByRole('group', { name: 'Selected file actions' }).getByRole('button', { name: 'Delete permanently', exact: true }).click();
    await expect(dialog.getByText(/This cannot be undone/)).toBeVisible();
    await dialog.getByRole('button', { name: 'Delete permanently', exact: true }).click();
    await expect(dialog).not.toBeVisible(); await expect(page.getByRole('heading', { name: 'Trash is empty' })).toBeVisible();
    await page.getByRole('button', { name: 'My files', exact: true }).click();
    await page.getByRole('button', { name: 'New folder', exact: true }).click();
    await dialog.getByLabel('Name', { exact: true }).fill('Projects');
    await dialog.getByRole('button', { name: 'New folder', exact: true }).click();
    await expect(dialog).not.toBeVisible();
    await expect(page.getByRole('button', { name: 'Projects(1)', exact: true })).toBeVisible();
    // Duplicate names in the same batch and a later upload are resolved by the API.
    await page.getByLabel('Choose files to upload', { exact: true }).setInputFiles([
      {name:'duplicate.txt', mimeType:'text/plain', buffer:Buffer.from('first')},
      {name:'duplicate.txt', mimeType:'text/plain', buffer:Buffer.from('second')}
    ]);
    await dialog.getByRole('button', {name:'Upload files', exact:true}).click();
    await expect(dialog).not.toBeVisible();
    await expect(page.getByRole('button', {name:'duplicate.txt', exact:true})).toBeVisible();
    await expect(page.getByRole('button', {name:'duplicate(1).txt', exact:true})).toBeVisible();
    await page.getByLabel('Choose files to upload', {exact:true}).setInputFiles({name:'duplicate.txt',mimeType:'text/plain',buffer:Buffer.from('third')});
    await dialog.getByRole('button', {name:'Upload files',exact:true}).click();
    await expect(dialog).not.toBeVisible();
    await expect(page.getByRole('button', {name:'duplicate(2).txt',exact:true})).toBeVisible();
    // Partial bulk failures preserve the destination and exclude completed items on retry.
    await page.getByRole('checkbox', { name: 'Select Brand guidelines.pdf', exact: true }).check();
    await page.getByRole('checkbox', { name: 'Select Budget 2026.csv', exact: true }).check();
    await page.getByRole('group', { name: 'Selected file actions' }).getByRole('button', { name: 'Copy', exact: true }).click();
    await dialog.getByRole('button', { name: 'Reports', exact: true }).click();
    let copies = 0;
    await page.route('**/api/file-storage/entries/*/copy', route => {
      copies += 1;
      return copies === 2 ? route.fulfill({status:409, contentType:'application/json', body:JSON.stringify({error:{code:'name_conflict'}})}) : route.continue();
    });
    await dialog.getByRole('button', { name: 'Copy to', exact: true }).click();
    await expect(dialog.getByRole('status')).toContainText('1 completed');
    await expect(dialog.getByRole('navigation', { name: 'Destination folder' }).getByRole('button', { name: 'Reports', exact: true })).toBeVisible();
    await dialog.getByLabel('Name', { exact: true }).fill('Recovered budget.csv');
    await dialog.getByRole('button', { name: 'Copy to', exact: true }).click();
    await expect(dialog).not.toBeVisible();
    await page.unroute('**/api/file-storage/entries/*/copy');
    expect(copies).toBe(3);
    await page.getByRole('button', { name: 'Reports', exact: true }).click();
    await expect(page.getByRole('button', { name: 'Brand guidelines.pdf', exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Recovered budget.csv', exact: true })).toBeVisible();
    await page.getByRole('navigation', { name: 'Current folder' }).getByRole('button', { name: 'My files', exact: true }).click();
    // A failed upload keeps its selected files available for an explicit retry.
    await page.route('**/api/file-storage/files', route => route.fulfill({status:502,contentType:'application/json',body:JSON.stringify({error:{code:'file_storage_upstream_error'}})}));
    await page.getByLabel('Choose files to upload', { exact: true }).setInputFiles({name:'retry-upload.txt',mimeType:'text/plain',buffer:Buffer.from('retry')});
    await dialog.getByRole('button', { name: 'Upload files', exact: true }).click();
    await expect(dialog.getByRole('alert')).toContainText('could not be reached');
    await page.unroute('**/api/file-storage/files');
    await dialog.getByRole('button', { name: 'Upload files', exact: true }).click();
    await expect(dialog).not.toBeVisible();
    await expect(page.getByRole('button', { name: 'retry-upload.txt', exact: true })).toBeVisible();
    await page.setViewportSize({ width: 760, height: 900 });
    await page.screenshot({ path: '/tmp/file-storage-narrow.png', fullPage: true });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.getByRole('combobox', { name: /language/i }).selectOption('ko');
    await expect(page.getByRole('heading', { name: '파일 보관함' })).toBeVisible();
    await page.screenshot({ path: '/tmp/file-storage-korean.png', fullPage: true });
    // A separate ordinary member gets an empty private filesystem through the same UI.
    const bob = await context.newPage();
    await context.clearCookies();
    await bob.goto('http://127.0.0.1:5187/file-storage');
    await bob.getByLabel('Username', { exact: true }).fill('bob'); await bob.getByLabel('Password', { exact: true }).fill('test-pass');
    await bob.getByRole('button', { name: 'Sign in', exact: true }).click();
    await expect(bob.getByRole('heading', { name: 'This folder is empty' })).toBeVisible();
    await expect(bob.getByRole('button', { name: 'Projects', exact: true })).toHaveCount(0);
    expect(failures).toEqual([]);
    console.log('PASS: real API login, folder create/rename/deep-link/reload/history, multi-upload, original-byte download, move/copy, search/details, trash/restore/bulk purge, automatic duplicate numbering and partial-bulk recovery, upload retry, responsive layout, Korean, member isolation.');
  } catch (error) { await page.screenshot({ path: '/tmp/file-storage-failure.png', fullPage: true }); throw error; }
  finally { await browser.close(); }
})().catch(error => { console.error(error); process.exit(1); });
