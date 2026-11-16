// Isolated composer smoke test: synthetic OCR/extraction responses; no record writes.
// Run with playwright available in NODE_PATH and AX768_PREVIEW_ORIGIN pointing to Vite.
const { chromium, expect } = require('playwright/test');
(async () => {
  const browser = await chromium.launch({headless:true,args:['--disable-features=LocalNetworkAccessChecks,LocalNetworkAccessChecksWebSockets'],executablePath:process.env.PLAYWRIGHT_CHROMIUM_PATH});
  try {
    const page = await browser.newPage({viewport:{width:1280,height:900}});
    const errors = [];
    page.on('pageerror', e => { errors.push(e.message); console.error('PAGE:', e.message); });
    page.on('console', m => { if (m.type() === 'error') console.error('CONSOLE:', m.text()); });
    await page.route('**/__ax-image-preview', route => route.fulfill({contentType:'text/html',body:`<!doctype html><html><head><meta name="viewport" content="width=device-width, initial-scale=1"></head><body><div id="root"></div><script type="module">
      import RefreshRuntime from '/@react-refresh';
      RefreshRuntime.injectIntoGlobalHook(window); window.$RefreshReg$ = () => {}; window.$RefreshSig$ = () => type => type; window.__vite_plugin_react_preamble_installed__ = true;
      const { default: React } = await import('/node_modules/.vite/deps/react.js');
      const { default: ReactDOM } = await import('/node_modules/.vite/deps/react-dom_client.js');
      const { Ax768WorkflowPanel } = await import('/src/features/agents/Ax768WorkflowPanel.tsx');
      ReactDOM.createRoot(document.getElementById('root')).render(React.createElement(Ax768WorkflowPanel));
    </script></body></html>`}));
    const rawText = "이름: 김순옥\n주소: 울진북로 164\n보호자 연락처: 010-0000-1234\nS/N: 00300016\n메모: 오후 연락";
    await page.route('**/src/features/agents/ax768Ocr.ts', route => route.fulfill({contentType:'text/javascript',body:`export async function extractImageText(files) { return files.map(file => ({filename:file.name,text:${JSON.stringify(rawText)},confidence:95})); }`}));
    let calls = 0, hold = false, fail = false, empty = false, release;
    await page.route('**/api/ax768/workflow/extract', async route => {
      calls++;
      const input = route.request().postDataJSON();
      expect(input.workflow_id).toBe('information_update');
      if (hold) await new Promise(resolve => { release = resolve; });
      try {
        await route.fulfill(fail ? {status:502,json:{detail:'failed'}} : {json:{workflow_id:'information_update',extraction_version:'1',fields:empty ? [] : input.sources.flatMap((source, source_index) => source.text.split('\n').filter(Boolean).map(line => ({label:line.split(':')[0],value:line.slice(line.indexOf(':')+1).trim(),source_index,uncertain:false})))}});
      } catch { /* An intentionally cancelled request may already be closed. */ }
    });
    let updateCalls = 0;
    await page.route('**/api/ax768/workflow/information-runs', async route => {
      updateCalls++;
      expect(route.request().postDataJSON()).toEqual({workflow_id:'information_update',message:'이름: 테스트가람\n주소: 테스트길 10\n요청사항: 생년월일 380215로 수정'});
      const stage = {status:'updated',reason:'저장 확인 완료',rows:[6],changes:['생년월일: 380215'],verified:true};
      await route.fulfill({json:{workflow_id:'information_update',id:'synthetic',region:'영덕',status:'completed',response:'가입자 명부, AS 처리와 마스터페이지 기록을 완료했습니다.',duration_ms:100,receipts:{roster:stage,as_update:{...stage,rows:[8,9]},member_note:{...stage,rows:[12]}}}});
    });
    await page.route('**/api/ax768/workflow/runs', () => { throw new Error('Extraction must never execute the device workflow'); });
    await page.goto(`${process.env.AX768_PREVIEW_ORIGIN || 'http://127.0.0.1:5173'}/__ax-image-preview`);
    const picker = page.locator('#ax-workflow-choice');
    const message = page.locator('#ax-workflow-message');
    await expect(picker).toBeVisible();
    const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a5XcAAAAASUVORK5CYII=','base64');
    async function paste(files, text = '') {
      return message.evaluate((element, {files,text}) => {
        const data = new DataTransfer();
        if (text) data.setData('text/plain', text);
        for (const file of files) data.items.add(new File([Uint8Array.from(atob(file.base64), c => c.charCodeAt(0))],file.name,{type:file.type,lastModified:1}));
        const event = new ClipboardEvent('paste',{clipboardData:data,bubbles:true,cancelable:true});
        element.dispatchEvent(event);
        return event.defaultPrevented;
      },{files,text});
    }
    await message.focus();
    expect(await paste([], 'plain text')).toBe(false);
    const screenshot = {name:'info.png',type:'image/png',base64:png.toString('base64')};
    expect(await paste([screenshot])).toBe(true);
    await expect(page.locator('li button[aria-haspopup=dialog] img').first()).toBeVisible();
    await page.locator('li button[aria-haspopup=dialog]').first().click();
    await expect(page.getByRole('dialog')).toBeVisible();
    await page.getByRole('dialog').getByRole('button').click();
    await expect(page.getByRole('dialog')).not.toBeVisible();
    // Re-pasting the same file obeys the existing duplicate guard.
    await paste([screenshot]);
    await expect(page.locator('li button[aria-haspopup=dialog] img')).toHaveCount(1);
    await expect(message).toHaveValue(rawText); expect(calls).toBe(0);
    hold = true;
    await picker.selectOption('information_update');
    await expect.poll(() => !!release).toBe(true);
    await expect(page.locator('#ax-structuring-status')).toHaveText('구조화 중…');
    await expect(message).toBeDisabled();
    await expect(message).toHaveAttribute('aria-busy', 'true');
    await expect(message).toHaveValue(rawText);
    hold = false; release(); release = undefined;
    await expect(page.locator('#ax-structuring-status')).toHaveText('구조화 완료 · 편집 가능');
    expect(await message.inputValue()).not.toContain('info.png');
    await expect(message).toHaveValue(/S\/N: 00300016/);
    await expect(message).toHaveValue(/보호자 연락처: 010-0000-1234/);
    expect(await message.inputValue()).not.toContain('신호확인');
    await expect(message).toBeEnabled(); expect(calls).toBe(1);
    await expect(page.getByRole('button',{name:'다시 추출',exact:true})).toHaveCount(0);
    await expect(page.getByText('원문 보기 · 구조화 전',{exact:true})).toHaveCount(0);
    await expect(page.getByText('에이전트가 제공된 모든 텍스트를 분석합니다. 추출한 내용을 원문과 비교해 확인해 주세요.',{exact:true})).toHaveCount(0);
    await expect(page.locator('#ax-workflow-setup-note')).toHaveCount(0);
    await picker.selectOption('device_adjustment_power');
    await expect(message).toHaveValue('이름: 김순옥\n주소: 울진북로 164\n요청: 신호확인'); expect(calls).toBe(1);
    hold = true;
    await picker.selectOption('information_update');
    await expect.poll(() => !!release).toBe(true);
    await picker.selectOption('device_adjustment_power');
    await expect(message).toHaveValue('이름: 김순옥\n주소: 울진북로 164\n요청: 신호확인');
    hold = false; release();
    await expect(message).toBeEnabled();
    expect(await message.inputValue()).not.toContain('010-0000-1234');
    fail = true;
    await picker.selectOption('information_update');
    await expect(page.locator('#ax-workflow-setup-note [role=alert]')).toBeVisible();
    await expect(message).toHaveValue(rawText);
    fail = false;
    await page.getByRole('button',{name:'입력 지우기',exact:true}).click();
    await expect(page.locator('#ax-structuring-status')).toHaveText('구조화 전');
    await message.fill('이름: 테스트가람\n연락처: 010-0000-5678');
    await page.getByRole('button',{name:'분석 및 추출',exact:true}).click();
    await expect(message).toHaveValue('이름: 테스트가람\n연락처: 010-0000-5678');
    await expect(message).toBeEnabled();
    await page.getByRole('button',{name:'입력 지우기',exact:true}).click();
    await message.fill('이름: 테스트가람\n주소: 테스트길 10\n요청사항: 생년월일 380215로 수정');
    await expect(page.locator('#ax-information-region')).toHaveCount(0);
    expect(updateCalls).toBe(0);
    await page.getByRole('button',{name:'워크플로 실행',exact:true}).click();
    await expect(page.getByText('가입자 명부, AS 처리와 마스터페이지 기록을 완료했습니다.',{exact:true})).toBeVisible();
    await expect(page.getByText('1. 가입자 명부 반영',{exact:true})).toBeVisible();
    expect(updateCalls).toBe(1);
    await page.getByRole('button',{name:'입력 지우기',exact:true}).click();
    empty = true;
    await message.fill('H\n[\nsg 744');
    await page.getByRole('button',{name:'분석 및 추출',exact:true}).click();
    await expect(page.locator('#ax-structuring-status')).toHaveText('추출할 업무 정보 없음');
    await expect(message).toHaveValue('');
    await expect(message).toBeEnabled();
    await expect(page.getByRole('button',{name:'분석 및 추출',exact:true})).toBeEnabled();
    await expect(page.getByRole('button',{name:'입력 지우기',exact:true})).toBeEnabled();
    await page.getByRole('button',{name:'입력 지우기',exact:true}).click();
    await expect(page.locator('#ax-structuring-status')).toHaveText('구조화 전');
    await expect(page.getByRole('button',{name:'분석 및 추출',exact:true})).toBeDisabled();
    expect(await paste([{name:'unsupported.gif',type:'image/gif',base64:png.toString('base64')}])).toBe(true);
    await expect(page.getByRole('alert')).toContainText('PNG');
    await expect(page.locator('li button[aria-haspopup=dialog] img')).toHaveCount(0);
    empty = false;
    await picker.selectOption('');
    await paste(Array.from({length:6}, (_,i) => ({...screenshot,name:`shot-${i}.png`})));
    await expect(page.locator('li button[aria-haspopup=dialog] img')).toHaveCount(5);
    await expect(page.getByRole('alert')).toContainText('5');
    await page.getByRole('button',{name:'입력 지우기',exact:true}).click();
    // File-picker uploads still work alongside clipboard input.
    await page.locator('input[type=file]').setInputFiles({name:'upload.png',mimeType:'image/png',buffer:png});
    await expect(page.locator('li button[aria-haspopup=dialog] img')).toHaveCount(1);
    await page.getByRole('button',{name:'입력 지우기',exact:true}).click();
    await picker.selectOption('information_update');
    await page.setViewportSize({width:390,height:700});
    await expect(page.getByRole('button',{name:'분석 및 추출',exact:true})).toBeVisible();
    console.log('PASS workflow-specific automatic extraction, simplified information UI, unchanged device template, stale response rejection, failure preservation, text-only extraction, empty/noise results without raw fallback, retry/clear narrow layout, automatic region lookup without a selector, separate information execution results, clipboard images, native text paste, popup preview, duplicate/type/count guards and file-picker uploads.');
    expect(errors).toEqual([]);

  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exit(1); });
