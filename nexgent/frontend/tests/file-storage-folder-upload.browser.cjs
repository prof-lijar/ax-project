// Requires the isolated tests.file_storage_smoke_server fixture on 8769 and Vite on 5187.
const { chromium, expect } = require('@playwright/test');
const fs = require('fs');
const os = require('os');
const path = require('path');
(async () => {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'nexgent-folder-browser-'));
  const localFolder = path.join(temp, 'Folder import');
  fs.mkdirSync(path.join(localFolder, 'Sub', 'Nested'), {recursive:true});
  fs.writeFileSync(path.join(localFolder, 'notes.md'), '# Folder notes');
  fs.writeFileSync(path.join(localFolder, 'Sub', 'data.txt'), 'child bytes');
  fs.writeFileSync(path.join(localFolder, 'Sub', 'Nested', '한글.txt'), 'nested bytes');
  const browser = await chromium.launch({headless:true,args:['--no-sandbox']});
  const context = await browser.newContext({viewport:{width:1440,height:1000},acceptDownloads:true});
  await context.addInitScript(() => { if(window === top) localStorage.setItem('nexgent.language','en'); });
  const page = await context.newPage();
  const errors = []; page.on('pageerror', error => errors.push(error.message));
  try {
    await page.goto('http://127.0.0.1:5187/file-storage');
    await page.getByLabel('Username',{exact:true}).fill('alice');
    await page.getByLabel('Password',{exact:true}).fill('test-pass');
    await page.getByRole('button',{name:'Sign in',exact:true}).click();
    await expect(page.getByRole('heading',{name:'File Storage',exact:true})).toBeVisible();
    await page.evaluate(async () => {
      const marker = await (await fetch('/api/file-storage-test-fixture')).json();
      if(marker.fixture !== 'isolated-file-storage-smoke') throw new Error('Wrong fixture');
      const me = await (await fetch('/api/me')).json();
      const list = await (await fetch('/api/file-storage/entries')).json();
      for(const item of list.items.filter(item => /^(Folder import|Dropped folder|Empty drop)(\(\d+\))?$/.test(item.name))) {
        await fetch('/api/file-storage/entries/'+item.id,{method:'DELETE',headers:{'X-CSRF-Token':me.csrf_token}});
      }
    });
    await page.getByRole('button',{name:'Refresh files',exact:true}).click();
    const dialog = page.getByRole('dialog');
    const upload = async () => {
      await page.getByLabel('Choose folder to upload',{exact:true}).setInputFiles(localFolder);
      await expect(dialog.getByText('Folder import/Sub/Nested/한글.txt',{exact:false})).toBeVisible();
      await dialog.getByRole('button',{name:'Upload files',exact:true}).click();
      await expect(dialog).not.toBeVisible();
    };
    await upload();
    await expect(page.getByRole('button',{name:'Folder import',exact:true})).toBeVisible();
    await upload();
    await expect(page.getByRole('button',{name:'Folder import(1)',exact:true})).toBeVisible();
    await page.getByRole('button',{name:'Folder import',exact:true}).click();
    await page.getByRole('button',{name:'Sub',exact:true}).click();
    await page.getByRole('button',{name:'data.txt',exact:true}).click();
    await expect(page.getByText('child bytes',{exact:true})).toBeVisible();
    const event = page.waitForEvent('download');
    await page.getByRole('button',{name:'Download',exact:true}).click();
    expect(fs.readFileSync(await (await event).path(),'utf8')).toBe('child bytes');
    await page.getByRole('button',{name:'Back to files',exact:true}).click();
    await page.getByRole('button',{name:'Nested',exact:true}).click();
    await expect(page.getByRole('button',{name:'한글.txt',exact:true})).toBeVisible();
    await page.getByRole('navigation',{name:'Current folder'}).getByRole('button',{name:'My files',exact:true}).click();
    const cdp = await context.newCDPSession(page);
    const drop = async emptyOnly => {
      const folder = path.join(temp, emptyOnly ? 'Empty drop' : 'Dropped folder');
      fs.mkdirSync(folder, {recursive:true});
      if (!emptyOnly) {
        fs.mkdirSync(path.join(folder,'Empty'), {recursive:true});
        fs.writeFileSync(path.join(folder,'drop.txt'),'dropped bytes');
      }
      const box = await page.locator('section[aria-labelledby="storage-title"]').boundingBox();
      const data = {items:[],files:[folder],dragOperationsMask:1};
      for (const type of ['dragEnter','dragOver','drop']) await cdp.send('Input.dispatchDragEvent',{type,x:box.x+100,y:box.y+150,data});
    };
    await drop(false);
    await expect(dialog.getByText('Dropped folder/drop.txt',{exact:false})).toBeVisible();
    // Retry preserves the complete folder selection and does not create a partial tree.
    await page.route('**/api/file-storage/files', route => route.fulfill({status:502,contentType:'application/json',body:JSON.stringify({error:{code:'file_storage_upstream_error'}})}));
    await dialog.getByRole('button',{name:'Upload files',exact:true}).click();
    await expect(dialog.getByRole('alert')).toContainText('could not be reached');
    await page.unroute('**/api/file-storage/files');
    await dialog.getByRole('button',{name:'Upload files',exact:true}).click();
    await expect(dialog).not.toBeVisible();
    await page.getByRole('button',{name:'Dropped folder',exact:true}).click();
    await page.getByRole('button',{name:'Empty',exact:true}).click();
    await expect(page.getByRole('heading',{name:'This folder is empty',exact:true})).toBeVisible();
    await page.getByRole('navigation',{name:'Current folder'}).getByRole('button',{name:'My files',exact:true}).click();
    await drop(true);
    await expect(dialog.getByText('1 folders included (including empty folders).',{exact:true})).toBeVisible();
    await dialog.getByRole('button',{name:'Upload files',exact:true}).click();
    await expect(dialog).not.toBeVisible();
    await expect(page.getByRole('button',{name:'Empty drop',exact:true})).toBeVisible();
    await page.setViewportSize({width:760,height:900});
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    await page.getByRole('combobox',{name:/language/i}).selectOption('ko');
    await expect(page.getByRole('button',{name:'폴더 업로드',exact:true})).toBeVisible();
    await page.screenshot({path:'/tmp/file-storage-folder-upload.png',fullPage:true});
    expect(errors).toEqual([]);
    console.log('PASS: real folder picker, nested paths, Korean filenames, duplicate root numbering, preview/original download, recursive drop, empty directories, retry, narrow Korean UI.');
  } catch(e) { await page.screenshot({path:'/tmp/file-storage-folder-failure.png',fullPage:true}); throw e; }
  finally { await browser.close(); fs.rmSync(temp,{recursive:true,force:true}); }
})().catch(e=>{console.error(e);process.exit(1);});
