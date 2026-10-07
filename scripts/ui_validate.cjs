#!/usr/bin/env node
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require(process.env.MEDIFLOW_PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.MEDIFLOW_UI_BASE || 'http://127.0.0.1:5097';
if (!/^http:\/\/127\.0\.0\.1:\d+$/.test(base)) throw new Error('Loopback fixture only');
const results=[];
let browser;
async function test(name, fn, viewport={width:1366,height:768}) {
  if(process.env.MEDIFLOW_UI_TEST_FILTER && !name.includes(process.env.MEDIFLOW_UI_TEST_FILTER))return;
  const context=await browser.newContext({viewport,reducedMotion:'reduce'});
  const external=[], errors=[], writes=[];
  await context.route('**/*',r=>{
    const u=new URL(r.request().url());
    if(u.origin===base || u.protocol==='data:') return r.continue();
    external.push(u.origin+u.pathname);
    return r.fulfill({status:200,contentType:'application/javascript',body:''});
  });
  const page=await context.newPage();page.setDefaultTimeout(8000);page.setDefaultNavigationTimeout(10000);
  page.on('pageerror',e=>errors.push(page.url().replace(base,'')+' '+e.stack));
  page.on('request',r=>{if(r.method()!=='GET') writes.push({path:new URL(r.url()).pathname,method:r.method()})});
  await context.addInitScript(()=>{if(!localStorage.getItem('i18n_language'))localStorage.setItem('i18n_language','ko');if(!localStorage.getItem('theme'))localStorage.setItem('theme','light');});
  try {await fn(page,context);assert.deepEqual(errors,[]);results.push({name,status:'PASS',errors,externalBlocked:external,writes});}
  catch(e){results.push({name,status:'FAIL',error:e.stack,errors,externalBlocked:external,writes});}
  finally{if(results[results.length-1].error)console.log(results[results.length-1].error);console.log(results[results.length-1].status+' '+name);await context.close();}
}
const go=(page,route)=>page.goto(base+route,{waitUntil:'load'});
(async()=>{
 browser=await chromium.launch({headless:true});
 try {
  await test('capabilities / all / focus / state',async page=>{
    await go(page,'/screening');
    const eye=page.locator('[data-modality="eye"]');await eye.waitFor();
    assert.equal(await page.locator('[data-modality="skin"]').isDisabled(),true);
    assert.equal(await page.locator('[data-modality="scalp"]').isDisabled(),true);
    await eye.click();assert.equal(await eye.getAttribute('aria-pressed'),'true');
    assert.equal(await eye.evaluate(e=>e===document.activeElement),true);
    await page.locator('#toggle-all').click();await page.locator('#toggle-all').click();
    await page.locator('#continue-button').click();
    await page.waitForURL('**/screening/survey');
    assert.deepEqual(await page.evaluate(()=>JSON.parse(sessionStorage.getItem('screening_plan'))),['eye']);
  });
  await test('capability failure ignores old ready cache / retry',async(page,context)=>{
    await context.addInitScript(()=>sessionStorage.setItem('screening_config_cache',JSON.stringify({status:'ok',modalities:[{id:'skin',model_status:'ready'}]})));
    await page.route('**/api/screening/config',r=>r.fulfill({status:503,contentType:'application/json',body:'{"status":"error"}'}));
    await go(page,'/screening');await page.locator('#retry-config').waitFor({state:'visible'});
    assert.equal(await page.locator('#continue-button').isDisabled(),true);
    assert.equal(await page.locator('#toggle-all').isDisabled(),true);
    await page.unroute('**/api/screening/config');await page.locator('#retry-config').click();
    await page.locator('[data-modality="eye"]').waitFor();
  });
  await test('identity / consent / dialog keyboard focus',async page=>{
    await go(page,'/login');await page.locator('#identifier').fill('synthetic@example.invalid');
    await page.locator('[type="submit"]').click();await page.locator('#confirm-toast.show').waitFor();
    assert.match(await page.locator('#confirm-toast-message').innerText(),/동의/);
    await page.keyboard.press('Tab');assert.equal(await page.locator('#confirm-toast-ok').evaluate(e=>e===document.activeElement),true);
    await page.locator('#confirm-toast-ok').click();await page.locator('#privacy-consent').check();
    await page.locator('[type="submit"]').click();await page.locator('#confirm-toast.show').waitFor();
    await page.locator('#confirm-toast-ok').click();await page.waitForURL('**/screening');
    assert.equal(await page.evaluate(()=>sessionStorage.getItem('user_id')),'synthetic@example.invalid');
  });
  if(!process.argv.includes('--stage2')) {
   await test('survey validation / exact payload / double submit / draft back',async(page,context)=>{
    await context.addInitScript(()=>{sessionStorage.setItem('user_id','synthetic@example.invalid');sessionStorage.setItem('screening_plan','["eye"]');sessionStorage.setItem('screening_active_modality','eye');});
    let posted=[];
    await page.route('**/api/survey',async r=>{if(r.request().method()==='POST'){posted.push(r.request().postDataJSON());await new Promise(resolve=>setTimeout(resolve,200));}await r.continue();});
    await go(page,'/screening/survey');await page.locator('#submit-button').click();assert.equal(posted.length,0);
    await page.locator('#age').fill('30');await page.locator('#eye-notes').fill('Synthetic note - no patient');
    await page.locator('input[value="건조함"]').check();
    await go(page,'/screening');await page.goBack({waitUntil:'load'});assert.equal(await page.locator('#age').inputValue(),'30');
    await page.locator('#submit-button').dblclick();await page.waitForURL('**/capture');assert.equal(posted.length,1);
    const survey=posted[0].survey;
    assert.deepEqual(survey.screening_types,['eye']);assert.equal(survey.screening_version,1);
    assert.deepEqual(survey.symptoms,['건조함']);assert.deepEqual(survey.eye.symptoms,['건조함']);
    assert.equal(survey.eye.notes,'Synthetic note - no patient');assert.ok(survey.skin && survey.scalp);
    assert.deepEqual(Object.keys(survey).sort(),['screening_version','screening_types','age','gender','conditions','smoking','drinking','other_notes','wearing','vision_left','vision_right','surgery_history','symptoms','eye','skin','scalp'].sort());
   });
   await test('camera missing / alignment / stale / reconnect',async page=>{
    let camera='missing';
    await page.route('**/detect_status',r=>r.fulfill({contentType:'application/json',body:JSON.stringify({detected:camera==='ready',confidence:.85,camera_state:camera==='ready'?'streaming':camera,frame_age_ms:camera==='stale'?5000:null})}));
    await go(page,'/capture');await page.waitForFunction(()=>document.querySelector('#status-message').textContent.includes('연결해'));
    assert.equal(await page.locator('#btn-capture-photo').isDisabled(),true);
    camera='ready';await page.waitForFunction(()=>document.querySelector('#status-message').textContent.includes('촬영할 수'));
    assert.equal(await page.locator('#btn-capture-photo').isDisabled(),false);
    camera='stale';await page.waitForFunction(()=>document.querySelector('#status-message').textContent.includes('멈췄'));
    assert.equal(await page.locator('#btn-capture-photo').isDisabled(),true);
    camera='ready';await page.waitForFunction(()=>document.querySelector('#status-message').textContent.includes('촬영할 수'));
   });
   await test('invalid upload / synthetic analysis / result',async(page,context)=>{
    await context.addInitScript(()=>sessionStorage.setItem('user_id','synthetic@example.invalid'));
    await go(page,'/capture');
    await page.locator('#upload-image-input').setInputFiles({name:'invalid.txt',mimeType:'text/plain',buffer:Buffer.from('synthetic invalid upload')});
    await page.waitForFunction(()=>document.querySelector('#capture-message').textContent.includes('지원') || document.querySelector('#capture-message').textContent.includes('형식'));
    assert.equal(await page.locator('#btn-go-result').isDisabled(),true);
    const image=await (await context.request.get(base+'/__fixture/image.png')).body();
    await page.locator('#upload-image-input').setInputFiles({name:'synthetic.png',mimeType:'image/png',buffer:image});
    await page.waitForFunction(()=>!document.querySelector('#btn-go-result').disabled);
    await page.locator('#btn-go-result').click();await page.waitForURL('**/result');
    assert.match(await page.locator('#ai-normal').innerText(),/73/);
   });
   await test('permission denied / slow poll no overlap / navigation abort',async page=>{
    let active=0,max=0,count=0;
    await page.route('**/detect_status',async r=>{active++;max=Math.max(max,active);count++;await new Promise(resolve=>setTimeout(resolve,650));active--;try{await r.fulfill({contentType:'application/json',body:JSON.stringify({detected:false,camera_state:'permission_denied'})});}catch(e){} });
    await go(page,'/capture');await page.waitForFunction(()=>document.querySelector('#status-message').textContent.includes('접근 권한'));
    assert.equal(await page.locator('#btn-capture-photo').isDisabled(),true);assert.equal(max,1);
    await go(page,'/screening');const previous=count;await page.waitForTimeout(1000);assert.equal(count,previous);
   });
   await test('mobile upload-only / touch controls / analysis',async(page,context)=>{
    await context.addInitScript(()=>Object.defineProperty(navigator,'userAgent',{get:()=> 'Mozilla/5.0 iPhone Mobile'}));
    const calls=[];page.on('request',r=>calls.push(new URL(r.url()).pathname));
    await go(page,'/capture');await page.waitForFunction(()=>document.body.classList.contains('mobile-upload-only'));
    assert.ok(!calls.includes('/detect_status'));assert.ok(!calls.includes('/camera/session/start'));
    const image=await (await context.request.get(base+'/__fixture/image.png')).body();
    await page.locator('#upload-image-input').setInputFiles({name:'synthetic.png',mimeType:'image/png',buffer:image});
    await page.waitForFunction(()=>!document.querySelector('#btn-go-result').disabled);
    assert.ok((await page.locator('#btn-go-result').boundingBox()).height>=56);
    await page.locator('#btn-go-result').click();await page.waitForURL('**/result');
   },{width:390,height:844});
   await test('result empty / no invented score / finish privacy / provider unavailable',async(page,context)=>{
    await go(page,'/result');assert.match(await page.locator('#ai-normal').innerText(),/분석 데이터 없음/);
    await page.locator('.ai-chat-fab').click();await page.waitForFunction(()=>document.querySelector('.ai-chat-input').disabled);
    assert.equal(await page.locator('.ai-chat-send').isDisabled(),true);
    assert.match(await page.locator('.ai-chat-messages').innerText(),/provider|준비/);
    const posts=[];page.on('request',r=>{if(r.method()==='POST')posts.push(new URL(r.url()).pathname)});
    await page.evaluate(()=>{sessionStorage.setItem('user_id','synthetic@example.invalid');localStorage.setItem('bilateral_analysis','synthetic-private');localStorage.setItem('user_id','synthetic@example.invalid');});
    await page.locator('.ai-chat-close').click();
    page.once('dialog',d=>d.accept());await page.locator('[data-mf-finish]').click();await page.waitForURL(base+'/');
    assert.equal(await page.evaluate(()=>sessionStorage.getItem('user_id')),null);
    assert.equal(await page.evaluate(()=>localStorage.getItem('bilateral_analysis')),null);
    assert.equal(await page.evaluate(()=>localStorage.getItem('user_id')),null);
    assert.equal(await page.evaluate(()=>localStorage.getItem('theme')),'light');assert.ok(!posts.includes('/api/chat'));
   });
   await test('history / synthetic share / PDF template / no external send',async(page,context)=>{
    await context.addInitScript(()=>{sessionStorage.setItem('user_id','synthetic@example.invalid');sessionStorage.setItem('user_age','30')});
    await go(page,'/report');await page.waitForFunction(()=>document.querySelector('#user-display').textContent.includes('synthetic@'));
    assert.match(await page.locator('body').innerText(),/73\.0%/);
    const share=await page.evaluate(()=>requestReportShare(false));assert.equal(share.status,'ok');assert.equal(share.share_url,'/__fixture/report');
    await go(page,'/report/pdf');assert.match(await page.locator('body').innerText(),/연구용/);
    const pdf=await page.pdf({format:'A4',printBackground:true});assert.ok(pdf.length>1000);
    fs.writeFileSync('/private/tmp/mediflow-ui-synthetic-browser.pdf',pdf);
   },{width:1024,height:768});
   await test('admin authentication / CSRF / Research disabled boundary',async(page,context)=>{
    assert.equal((await context.request.get(base+'/admin/config')).status(),401);
    assert.equal((await context.request.post(base+'/api/admin/config',{data:{}})).status(),401);
    await context.request.post(base+'/api/admin/login',{data:{password:'synthetic-admin'}});
    assert.equal((await context.request.post(base+'/api/admin/config',{data:{},headers:{'X-Admin-CSRF':'wrong'}})).status(),403);
    await go(page,'/admin/ai-experiments');await page.waitForFunction(()=>document.querySelector('#capabilities').textContent.length>0);
    assert.equal(await page.locator('#import-button').isDisabled(),true);assert.equal(await page.locator('#compare-button').isDisabled(),true);
    assert.match(await page.locator('body').innerText(),/Research/);
   });
   await test('draft / plan diff / deny / browser-only mock Apply',async(page,context)=>{
    await context.request.post(base+'/api/admin/login',{data:{password:'synthetic-admin'}});
    await go(page,'/admin/config');await page.locator('#ai-save-draft').waitFor();
    await page.waitForFunction(()=>!document.querySelector('#ai-save-draft').disabled);
    await page.locator('#ai-save-draft').click();await page.waitForFunction(()=>!document.querySelector('#ai-plan').disabled);
    await page.locator('#ai-plan').click();await page.waitForFunction(()=>document.querySelector('#ai-plan-diff').textContent.includes('mutations_disabled'));
    assert.equal(await page.locator('#ai-apply').isDisabled(),true);
    let applied=[];
    await page.route('**/operations',r=>{applied.push({body:r.request().postDataJSON(),csrf:r.request().headers()['x-admin-csrf']});return r.fulfill({contentType:'application/json',body:'{"status":"ok","operation":{"operation_id":"0123456789abcdef0123456789abcdef"}}'})});
    await page.route('**/operations/0123456789abcdef0123456789abcdef',r=>r.fulfill({contentType:'application/json',body:'{"status":"ok","operation":{"state":"succeeded","stage":"mock-only"}}'}));
    await page.evaluate(()=>{configState.aiControl.mutations_enabled=true;aiControlState.overview.capabilities.mutations_enabled=true;aiControlState.plan.blocking_reasons=[];aiControlState.plan.expires_at=new Date(Date.now()+60000).toISOString();aiControlState.plan.plan_digest='synthetic-digest';updateRuntimeApplyButton()});
    assert.equal(await page.locator('#ai-apply').isDisabled(),false);
    await page.locator('#ai-apply').click();await page.locator('#confirm-toast.show').waitFor();assert.equal(applied.length,0);
    await page.locator('#confirm-toast-ok').click();await page.waitForFunction(()=>document.querySelector('#ai-plan-result').textContent.includes('mock-only'));
    assert.equal(applied.length,1);assert.equal(applied[0].csrf,'fixture-csrf');assert.equal(applied[0].body.plan_id,'fixture-plan');
    await page.locator('summary').filter({hasText:'카메라 관측'}).click();await page.getByRole('button',{name:'관측 새로고침'}).click();await page.waitForFunction(()=>document.querySelector('#camera-observation').textContent.includes('frame_age_ms'));
    await page.locator('#camera-mesh-view').click();await page.locator('#camera-mesh-frame').waitFor({state:'visible'});
    assert.match(await page.locator('#camera-mesh-frame').getAttribute('src'),/mesh=1/);await page.getByRole('button',{name:'프레임 닫기'}).click();assert.equal(await page.locator('#camera-mesh-frame').getAttribute('src'),null);
   });
   await test('mobile PIN error / verification / dashboard access',async(page,context)=>{
    await go(page,'/m');await page.locator('#pin-input').fill('1111');await page.locator('#verify-btn').click();
    await page.waitForFunction(()=>document.querySelector('#msg').textContent.includes('rejected'));
    await page.locator('#pin-input').fill('1234');await page.locator('#verify-btn').click();await page.waitForURL('**/m/dashboard?request_id=synthetic-session');
    await page.getByRole('button',{name:'검사 선택 화면 열기'}).click();await page.waitForURL('**/screening');
   },{width:390,height:844});
   await test('remaining active routes / dormant mobile / not-configured direct path',async(page,context)=>{
    await context.addInitScript(()=>{sessionStorage.setItem('user_id','synthetic@example.invalid');sessionStorage.setItem('screening_plan','["skin"]');sessionStorage.setItem('screening_active_modality','skin')});
    for(const route of ['/survey','/training','/screening/capture','/screening/result','/screening/summary','/__fixture/template/m_index','/__fixture/template/m_login_start','/__fixture/template/m_survey','/__fixture/template/m_capture','/__fixture/template/m_result','/__fixture/template/m_report']) {
     await go(page,route);await page.waitForTimeout(550);assert.match(await page.locator('body').innerText(),/MediFlow/);
    }
    await go(page,'/screening/result');assert.match(await page.locator('body').innerText(),/모델|준비|분석/);
   });
   await test('theme / six languages / keyboard / doubled UI / contrast',async page=>{
    await go(page,'/');
    for(const lang of ['ko','en','zh','vi','ru','ja']) {
     await page.evaluate(lang=>{localStorage.setItem('i18n_language',lang);localStorage.setItem('theme','dark')},lang);
     await page.reload({waitUntil:'load'});await page.waitForTimeout(350);
     assert.equal(await page.evaluate(()=>document.documentElement.dataset.theme),'dark');
     assert.equal(await page.evaluate(()=>i18n.currentLanguage),lang);
     assert.ok((await page.locator('.mf-steps').innerText()).length>15);
    }
    await page.evaluate(()=>{localStorage.setItem('i18n_language','ko');localStorage.setItem('theme','light')});
    await page.reload({waitUntil:'load'});await page.keyboard.press('Tab');
    assert.equal(await page.locator('.mf-skip').evaluate(e=>e===document.activeElement),true);
    const ratios=await page.evaluate(()=>{
      const linear=x=>{x/=255;return x<=.04045?x/12.92:((x+.055)/1.055)**2.4};
      const lum=hex=>{const a=hex.match(/[a-f0-9]{2}/gi).map(x=>linear(parseInt(x,16)));return a[0]*.2126+a[1]*.7152+a[2]*.0722};
      const contrast=(a,b)=>{const x=lum(a),y=lum(b);return (Math.max(x,y)+.05)/(Math.min(x,y)+.05)};
      return {primary:contrast('146b65','ffffff'),text:contrast('173534','f6f8f5'),muted:contrast('526764','ffffff'),dark:contrast('edf5f1','18312e')};
    });assert.ok(Object.values(ratios).every(x=>x>=4.5));
    await page.evaluate(()=>document.body.style.zoom='2');
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=document.documentElement.clientWidth+2));
    await page.locator('.btn-start').scrollIntoViewIfNeeded();assert.ok((await page.locator('.btn-start').boundingBox()).height>=112);
   });
   await test('capability text safety / no fabricated skin result',async page=>{
    await page.route('**/api/screening/config',r=>r.fulfill({contentType:'application/json',body:JSON.stringify({status:'ok',modalities:[{id:'skin',label:'<img src=x onerror="window.injected=true">',model_status:'not_configured',input_mode:'upload',capture_route:'/screening/capture',result_route:'/screening/result'}]})}));
    await go(page,'/screening');await page.locator('[data-modality="skin"]').waitFor();
    assert.equal(await page.locator('[data-modality="skin"]').isDisabled(),true);assert.equal(await page.evaluate(()=>!!window.injected),false);
    assert.equal(await page.locator('[data-modality="skin"] img').count(),0);
   });
   for(const viewport of [{width:1920,height:1080},{width:1366,height:768},{width:1024,height:768},{width:390,height:844},{width:683,height:384},{width:390,height:420}]) {
    await test(`viewport ${viewport.width}x${viewport.height} / long text / scroll / focus`,async(page,context)=>{
     await context.request.post(base+'/api/admin/login',{data:{password:'synthetic-admin'}});
     await context.addInitScript(()=>{sessionStorage.setItem('screening_plan','["eye"]');sessionStorage.setItem('screening_active_modality','eye');});
     for(const route of ['/','/login','/screening','/screening/survey','/capture','/result','/report','/m','/m/dashboard','/admin/config','/admin/ai-experiments']) {
      await go(page,route);await page.waitForTimeout(350);
      const metrics=await page.evaluate(()=>({width:document.documentElement.clientWidth,scroll:document.documentElement.scrollWidth}));
      assert.ok(metrics.scroll<=metrics.width+2,route+' horizontal overflow '+JSON.stringify(metrics));
     }
     await go(page,'/screening/survey');await page.locator('#eye-notes').fill('Synthetic long note '.repeat(80));await page.locator('#submit-button').focus();
     assert.equal(await page.locator('#submit-button').evaluate(e=>e===document.activeElement),true);
     await page.locator('#submit-button').scrollIntoViewIfNeeded();assert.ok((await page.locator('#submit-button').boundingBox()).height>=56);
    },viewport);
   }
  }
 } finally {await browser.close();}
 const output=path.join(__dirname,'../docs/ui-redesign/logs',process.argv.includes('--stage2')?'stage2-browser.json':'validation-browser.json');
 fs.writeFileSync(output,JSON.stringify(results,null,2));console.log(JSON.stringify(results,null,2));
 if(results.some(x=>x.status!=='PASS'))process.exitCode=1;
})().catch(e=>{console.error(e);process.exit(1)});
