// All product API responses are synthetic; no AS, Sheets or member records are changed.
import assert from 'node:assert/strict';
import {mkdir} from 'node:fs/promises';
const {chromium} = await import(process.env.PLAYWRIGHT_MODULE ?? 'playwright');
const base = process.env.AX768_TEST_URL ?? 'http://127.0.0.1:5173';
const artifacts = process.env.AX768_TEST_ARTIFACTS ?? '/tmp/ax768-ui-artifacts';
await mkdir(artifacts, {recursive: true});
const browser = await chromium.launch({headless: true, executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE});
try {
  const page = await browser.newPage({viewport: {width:1280, height:900}});
  page.setDefaultTimeout(10000);
  const errors = [], calls = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.addInitScript(() => { if (!localStorage.getItem('nexgent.language')) localStorage.setItem('nexgent.language', 'ko'); });
  await page.route(url => /^\/(api|rag-api|scout-api|weekly-report-bulk-api|agent-server)\//.test(url.pathname), route => route.fulfill({json:{items:[],conversations:[],messages:[],ok:true}}));
  await page.route('**/api/me', route => route.fulfill({json:{id:'preview',username:'preview',name:'Preview',email:'',roles:[],permissions:[],is_admin:true,csrf_token:'mock'}}));
  let release;
  const held = new Promise(resolve => {release = resolve;});
  const stage = {status:'skipped',row:null,sheet_alias:null,city:null,sheet_title:null,name:null,address:null,reason:null,sheet_url:null};
  const candidate = {...stage,status:'candidate',row:10,name:'홍길동',address:'테스트로 1',city:'울진',sheet_alias:'uljin-users',sheet_url:'https://docs.google.com/spreadsheets/d/test/edit#gid=0&range=A10'};
  await page.route('**/api/ax768/workflow/runs', async route => {
    calls.push(route.request().postDataJSON());
    if (calls.length === 1) await held;
    await route.fulfill({json:{workflow_id:'device_adjustment_power',id:'test',started_at:'2026-11-11T00:00:00Z',duration_ms:10,
      status:calls.length === 1 ? 'needs_confirmation' : 'not_found',response:'브라우저 검증 결과',
      parsed:{name:'홍길동',lookup_name:'홍길동',address:'테스트로 1',mode:'person'},
      roster:stage,as_lookup:stage,as_update:{status:'skipped',row:null,date:null,changes:[],y_action:null,verified:false,reason:null},
      signal:{status:'skipped',imei_column:null,imei:null,sn:null,connected:null,fresh:null,signal_label:null,rssi:null,reason:null},member_note:null,
      candidates:calls.length === 1 ? [candidate] : [],notices:[],attempts:[]}});
  });
  await page.goto(`${base}/agents/ax768`);
  const select = page.locator('#ax-workflow-choice');
  const run = page.getByRole('button', {name:'워크플로 실행', exact:true});
  assert.equal(await page.locator('#ax-tab-workflow').getAttribute('aria-selected'), 'true');
  assert.equal(await page.locator('#ax-panel-test').isVisible(), false);
  assert.equal(await page.locator('#ax-workflow-status-title').count(), 0);
  assert.equal(await select.inputValue(), '');
  assert.equal(await select.locator('option:disabled').count(), 5);
  for (const width of [1280, 820, 390]) {
    await page.setViewportSize({width, height:900});
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await page.screenshot({path:`${artifacts}/workflow-${width}.png`,fullPage:true});
  }
  await page.setViewportSize({width:1280,height:900});
  assert.equal(await page.getByText('입력 도움말', {exact:true}).count(), 0);
  // Tabs remain keyboard operable.
  const workflowTab = page.locator('#ax-tab-workflow');
  await workflowTab.focus(); await workflowTab.press('ArrowRight');
  assert.equal(await page.locator('#ax-tab-test').getAttribute('aria-selected'), 'true');
  assert.equal(await page.locator('#ax-case').isVisible(), true);
  const help = page.getByText('작업 안내', {exact:true});
  await help.focus(); await help.press('Enter');
  assert.equal(await help.evaluate(el => el.parentElement.open), true);
  await help.press('Enter');
  await page.locator('#ax-tab-test').press('End');
  assert.equal(await page.locator('#ax-tab-sheets').getAttribute('aria-selected'), 'true');
  for (const width of [1280,390]) {
    await page.setViewportSize({width,height:900});
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await page.screenshot({path:`${artifacts}/sheets-${width}.png`,fullPage:true});
  }
  await page.locator('#ax-tab-sheets').focus(); await page.locator('#ax-tab-sheets').press('Home');
  await run.click();
  await page.getByRole('alert').filter({hasText:'워크플로를 먼저 선택해 주세요.'}).waitFor();
  assert.equal(await select.evaluate(el => el === document.activeElement), true);
  assert.equal(calls.length, 0);
  await select.selectOption('device_adjustment_power');
  await page.locator('#ax-workflow-message').fill('테스트로 1 홍길동');
  await run.click();
  await page.waitForFunction(() => document.querySelector('#ax-workflow-choice').disabled);
  assert.equal(await page.locator('#ax-workflow-message').isDisabled(), true);
  release();
  await page.getByRole('button', {name:/홍길동/}).click();
  await page.waitForFunction(() => !document.querySelector('#ax-workflow-choice').disabled);
  assert.equal(calls.length, 2);
  assert.deepEqual(calls[0], {workflow_id:'device_adjustment_power',message:'테스트로 1 홍길동',confirmed_name:null});
  assert.equal(calls[1].confirmed_name, '홍길동');
  const receipts = page.locator('#ax-panel-workflow details').filter({has:page.locator('summary', {hasText:'1. 가입자 명부'})});
  assert.equal(await receipts.getAttribute('open'), null);
  await page.locator('#ax-tab-test').click();
  await page.screenshot({path:`${artifacts}/individual-390.png`,fullPage:true});
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  await page.locator('#ax-tab-workflow').click();
  assert.equal(await select.inputValue(), 'device_adjustment_power');
  assert.equal(await page.locator('#ax-workflow-message').inputValue(), '테스트로 1 홍길동');
  await page.getByRole('button', {name:'입력 지우기', exact:true}).click();
  assert.equal(await select.inputValue(), 'device_adjustment_power');
  await run.click();
  await page.getByRole('alert').filter({hasText:'1~8,000자의 메시지를 입력해 주세요.'}).waitFor();
  assert.equal(await page.locator('#ax-workflow-message').evaluate(el => el === document.activeElement), true);
  assert.equal(calls.length, 2);
  await page.reload();
  await select.waitFor();
  assert.equal(await select.inputValue(), '');
  assert.equal(await workflowTab.getAttribute('aria-selected'), 'true');
  await page.evaluate(() => localStorage.setItem('nexgent.language', 'en'));
  await page.reload(); await select.waitFor();
  assert.equal(await page.getByRole('heading', {name:'New request',exact:true}).isVisible(), true);
  for (const width of [1280, 820, 390]) {
    await page.setViewportSize({width, height:900});
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await page.screenshot({path:`${artifacts}/english-${width}.png`,fullPage:true});
  }
  assert.deepEqual(errors, []);
  console.log('PASS default workflow, keyboard tabs/details, required fields, locked execution, candidate retry, collapsed receipts, draft persistence, clear/reload and responsive views. All APIs mocked.');
} finally { await browser.close(); }
