// Optional real Korean OCR smoke check; all product APIs are mocked.
import { mkdirSync, writeFileSync } from "node:fs";
import assert from "node:assert/strict";
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE ?? "playwright");
const base = process.env.AX768_OCR_URL ?? "http://127.0.0.1:5173";
const artifacts = process.env.AX768_OCR_ARTIFACTS ?? "/tmp/ax768-ocr-artifacts";
mkdirSync(artifacts, { recursive: true });
(async () => {
 const browser = await chromium.launch({headless:true,executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE});
 try {
  const page = await browser.newPage({viewport:{width:1280,height:1000}});
  await page.addInitScript(() => localStorage.setItem("nexgent.language", "ko"));
  await page.route(url => /^\/(api|rag-api|weekly-report-bulk-api|scout-api|scout-scheduler-api)\//.test(url.pathname), route => route.fulfill({json:{items:[],conversations:[],messages:[],jobs:[],next_cursor:null,ok:true}}));
  await page.route("**/api/me", route => route.fulfill({json:{id:"ocr-smoke",username:"test",name:"OCR check",email:"",roles:[],permissions:["access.manage"],is_admin:true,csrf_token:"test-only"}}));
  await page.route("**/agent-server/ok", route => route.fulfill({json:{ok:true}}));
  const errors=[], external=[], requests=[];
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => { if (!request.url().startsWith(base) && !request.url().startsWith('data:') && !request.url().startsWith('blob:')) external.push(request.url()); });
  await page.route('**/api/ax768/workflow/runs', async route => { requests.push(route.request().postDataJSON()); await route.fulfill({status:502,json:{detail:'synthetic stop; no real device or AS access'}}); });
  await page.goto(`${base}/agents/ax768`);
  await page.locator('#ax-tab-workflow').click();
  const png = await page.evaluate(() => {
   const canvas=document.createElement('canvas'); canvas.width=1100; canvas.height=400;
   const ctx=canvas.getContext('2d');ctx.fillStyle='#ddd';ctx.fillRect(0,0,1100,400);
   ctx.fillStyle='#777';ctx.font='48px "Noto Sans CJK KR"';
   ctx.fillText('이름: 김 순 옥',55,100);ctx.fillText('주소: 울진북로 164',55,200);ctx.fillText('요청: 신호확인',55,300);
   return canvas.toDataURL('image/png').split(',')[1];
  });
  const bytes=Buffer.from(png,'base64');writeFileSync(`${artifacts}/korean-fixture.png`,bytes);
  await page.locator('input[type=file]').setInputFiles({name:'korean-fixture.png',mimeType:'image/png',buffer:bytes});
  await page.waitForFunction(() => document.querySelector('#ax-workflow-message').value.startsWith('이름:'),{},{timeout:120000});
  const value=await page.locator('#ax-workflow-message').inputValue();console.log('Extracted input:',value);
  assert(value.includes('이름: 김순옥'));assert(value.includes('주소: 울진북로 164'));assert.equal(requests.length,0);
  await page.locator('details summary').click();await page.screenshot({path:`${artifacts}/desktop.png`,fullPage:true});
  await page.locator('#ax-workflow-choice').selectOption('device_adjustment_power');
  // A low-confidence result requires a deliberate correction; the fixture should be high confidence.
  await page.getByRole('button',{name:'워크플로 실행',exact:true}).click();
  await page.waitForTimeout(300);
  if (!requests.length) { console.log('Review requirement:',await page.locator('#ax-workflow-setup-note').innerText()); throw new Error('Unexpected review block for clear Korean fixture'); }
  assert.equal(requests[0].message,'울진북로 164 김순옥님 신호확인요.');assert(!('images' in requests[0]));
  await page.setViewportSize({width:390,height:900});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));await page.screenshot({path:`${artifacts}/mobile.png`,fullPage:true});
  // Removal restores the original typed input and prevents a stale completion.
  await page.getByRole('button',{name:'입력 지우기',exact:true}).click();
  await page.locator('#ax-workflow-message').fill('김순옥님 신호확인요.');
  await page.locator('input[type=file]').setInputFiles({name:'again.png',mimeType:'image/png',buffer:bytes});
  await page.getByRole('button',{name:'again.png 삭제',exact:true}).click();
  await page.waitForTimeout(1500);
  assert.equal(await page.locator('#ax-workflow-message').inputValue(),'김순옥님 신호확인요.');
  assert.deepEqual(external,[]);assert.deepEqual(errors,[]);
  console.log('PASS actual Korean OCR, enhancement, structured prefill, explicit Run, text-only payload, mobile, removal cancellation; zero external uploads.');
 } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exit(1)});
