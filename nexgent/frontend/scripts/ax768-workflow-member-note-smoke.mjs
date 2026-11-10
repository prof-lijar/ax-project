// Every product API is mocked. This script never changes an AS or member record.
import assert from 'node:assert/strict';
import {mkdir} from 'node:fs/promises';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE ?? 'playwright');
const base=process.env.AX768_TEST_URL ?? 'http://127.0.0.1:5173';
const artifacts=process.env.AX768_TEST_ARTIFACTS ?? '/tmp/ax768-workflow-member-note-artifacts';
await mkdir(artifacts,{recursive:true});
const browser=await chromium.launch({headless:true,executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE});
try {
 const page=await browser.newPage({viewport:{width:1280,height:1000}});
 await page.addInitScript(()=>localStorage.setItem('nexgent.language','ko'));
 await page.route(url=>/^\/(api|rag-api|scout-api|weekly-report-bulk-api)\//.test(url.pathname),r=>r.fulfill({json:{items:[],conversations:[],messages:[],ok:true}}));
 await page.route('**/api/me',r=>r.fulfill({json:{id:'test',username:'test',name:'Workflow test',email:'',roles:[],permissions:['access.manage'],is_admin:true,csrf_token:'test'}}));
 await page.route('**/agent-server/ok',r=>r.fulfill({json:{ok:true}}));
 const errors=[],calls=[];page.on('pageerror',e=>errors.push(e.message));
 let scenario='adjust';
 await page.route('**/api/ax768/workflow/runs',async route=>{
  calls.push(route.request().postDataJSON());
  const stage={status:'found',row:44,sheet_alias:'uljin-users',city:'울진군',sheet_title:'명부',name:'김순옥',address:'울진북로164',reason:null,sheet_url:'https://docs.google.com/spreadsheets/d/test/edit#gid=7&range=A44'};
  const missing=scenario==='power', uncertain=scenario==='unknown', disconnected=scenario==='disconnected';
  const note=`2026-11-10 [현지관리자 방문] ${missing?'전원연결':'기기위치조정'}`;
  const skipped={status:'skipped',row:null,date:null,changes:[],y_action:null,verified:false,reason:'AS 업데이트 건너뜀'};
  const result={workflow_id:'device_adjustment_power',id:'test-'+calls.length,started_at:'2026-11-10',duration_ms:100,status:disconnected?'disconnected':uncertain?'failed':'completed',response:note,parsed:{name:'김순옥',lookup_name:'김순옥',address:'울진북로164',mode:'name_address'},roster:stage,as_lookup:missing||disconnected?{...stage,status:missing?'not_found':'skipped',row:null,sheet_url:null}:{...stage,sheet_alias:'AS'},as_update:missing||disconnected?skipped:{status:'updated',row:44,date:'2026-11-10',changes:[{column:'S',value:'처리완료'},{column:'X',value:'2026-11-10'}],y_action:'unchanged',verified:true,reason:'AS 처리완료'},signal:{status:disconnected?'disconnected':'connected',imei_column:'AA',imei:'861212072106726',sn:'00300016',connected:!disconnected,fresh:!disconnected,signal_label:null,rssi:null,reason:null},member_note:disconnected?null:{status:uncertain?'unknown':'saved',member_id:12,name:'김순옥',address:'울진북로164',note,verified:!uncertain,candidates:[]},attempts:[],notices:[],candidates:[]};
  await route.fulfill({json:result});
 });
 await page.goto(`${base}/agents/ax768`);
 await page.locator('#ax-tab-workflow').click();
 await page.locator('#ax-workflow-choice').selectOption('device_adjustment_power');
 const run=page.getByRole('button',{name:'워크플로 실행',exact:true});
 const noteStage=page.getByRole('region',{name:'5. 가입자 일반 사항',exact:true});
 for (const choice of ['adjust','power','unknown','disconnected']) {
  scenario=choice;
  await page.locator('#ax-workflow-message').fill(`울진북로 164 김순옥님 ${choice==='power'?'전원연결':'기기위치조정'} 신호확인요`);
  await run.click();
  await noteStage.waitFor();
  if(choice==='disconnected') await noteStage.getByText('건너뜀',{exact:true}).waitFor();
  else if(choice==='unknown') await noteStage.getByText('다시 실행하기 전에 가입자 일반 사항을 확인해 주세요. 이미 저장되었을 수 있습니다.',{exact:true}).waitFor();
  else {
   await noteStage.getByText(`2026-11-10 [현지관리자 방문] ${choice==='power'?'전원연결':'기기위치조정'}`,{exact:true}).waitFor();
   await noteStage.getByText('저장 확인 완료',{exact:true}).waitFor();
   assert.equal(await noteStage.locator('a').getAttribute('href'),'https://admin.ansimk.com/members');
   await page.screenshot({path:`${artifacts}/${choice}.png`,fullPage:true});
  }
 }
 assert.equal(calls.length,4);
 await page.setViewportSize({width:390,height:900});
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 await page.screenshot({path:`${artifacts}/mobile.png`,fullPage:true});
 assert.deepEqual(errors,[]);
 console.log('PASS workflow member stage: adjustment, power/no-AS, unknown, disconnected, mobile. All product APIs mocked.');
} finally {await browser.close()}
