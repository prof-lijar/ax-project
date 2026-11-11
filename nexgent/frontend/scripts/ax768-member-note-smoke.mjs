// Browser smoke test: every product API is mocked; never writes a member record.
import assert from 'node:assert/strict';
import {mkdir} from 'node:fs/promises';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE ?? 'playwright');
const base=process.env.AX768_TEST_URL ?? 'http://127.0.0.1:5173';
const artifacts=process.env.AX768_TEST_ARTIFACTS ?? '/tmp/ax768-member-note-artifacts';
await mkdir(artifacts,{recursive:true});
const browser=await chromium.launch({headless:true,executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE});
try {
 const page=await browser.newPage({viewport:{width:1280,height:1000}});
 await page.addInitScript(()=>localStorage.setItem('nexgent.language','ko'));
 await page.route(url=>/^\/(api|rag-api|scout-api|weekly-report-bulk-api)\//.test(url.pathname),r=>r.fulfill({json:{items:[],conversations:[],messages:[],ok:true}}));
 await page.route('**/api/me',r=>r.fulfill({json:{id:'test',username:'test',name:'Member note test',email:'',roles:[],permissions:['access.manage'],is_admin:true,csrf_token:'test'}}));
 await page.route('**/agent-server/ok',r=>r.fulfill({json:{ok:true}}));
 const calls=[];const errors=[];page.on('pageerror',e=>errors.push(e.message));
 let outcome='saved';
 const note='2026-10-28 [현지관리자 방문] 기기위치조정';
 await page.route('**/api/ax768/runs',async route=>{
  const body=route.request().postDataJSON();calls.push(body);assert.equal(body.case_id,'member_note');
  const saved=outcome==='saved'||outcome==='present';
  const candidate=outcome==='candidate';
  const result={id:'test-'+calls.length,case_id:'member_note',status:candidate?'blocked':saved?'completed':'failed',outcome:candidate?'blocked':outcome==='present'?'note_present':saved?'note_saved':'unknown',response:candidate?'가입자를 선택해 주세요.':saved?'일반 사항 저장 확인':'저장되었을 수 있으므로 재실행 전에 일반 사항을 확인해 주세요.',started_at:'2026-11-10',duration_ms:100,city:null,sheet_alias:null,sheet_title:null,selected_row:null,name:'넥스터_이은경',address:'테스트로 1',sheet_url:null,highlighted_range:null,stored_verified:null,visible_verified:null,overridden_cells:[],overridden_cell_count:0,match_count:candidate?2:0,matches:[],attempts:[],member_note:{status:candidate?'needs_confirmation':outcome==='present'?'already_present':saved?'saved':'unknown',member_id:candidate?null:12,name:'넥스터_이은경',address:'테스트로 1',note,verified:saved,candidates:candidate?[{member_id:12,name:'넥스터_이은경',address:'테스트로 1'},{member_id:13,name:'테스트_이은경',address:'다른길 2'}]:[]}};
  await route.fulfill({json:result});
 });
 await page.goto(process.env.AX768_TEST_PAGE ?? `${base}/agents/ax768`);
 await page.locator('#ax-case').selectOption('member_note');
 await page.getByRole('button',{name:'예시 입력',exact:true}).click();
 const run=page.getByRole('button',{name:'가입자 검색 및 일반 사항 교체',exact:true});
 await run.click();
 await page.getByText('일반 사항 저장 확인',{exact:true}).first().waitFor();
 assert.equal(calls.length,1);assert(calls[0].message.includes('이름: 이은경'));
 assert.equal(await page.getByRole('button',{name:/가입자 선택:/}).count(),0);
 outcome='candidate';await run.click();
 await page.getByRole('button',{name:/가입자 선택: 넥스터_이은경/}).click();
 assert.equal(calls.length,2,'Selecting a candidate must not save automatically');
 assert((await page.locator('#ax-message').inputValue()).includes('가입자 ID: 12'));
 outcome='saved';await run.click();await page.getByText('일반 사항 저장 확인',{exact:true}).first().waitFor();
 assert.equal(calls.length,3);assert(calls[2].message.includes('이름: 넥스터_이은경'));
 await page.screenshot({path:`${artifacts}/saved.png`,fullPage:true});
 outcome='present';await run.click();await page.getByText('이미 기록된 메모',{exact:true}).first().waitFor();assert.equal(calls.length,4);
 outcome='unknown';await run.click();await page.getByText('저장되었을 수 있으므로 재실행 전에 일반 사항을 확인해 주세요.',{exact:true}).first().waitFor();assert.equal(calls.length,5);
 await page.setViewportSize({width:390,height:900});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 await page.screenshot({path:`${artifacts}/mobile.png`,fullPage:true});assert.deepEqual(errors,[]);
 console.log('PASS member note replacement case, direct unique-member save, ambiguous candidate selection, unchanged receipt, unknown outcome and mobile layout. Product API mocked.');
} finally {await browser.close()}
