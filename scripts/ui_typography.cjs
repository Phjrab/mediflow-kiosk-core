#!/usr/bin/env node
// Actual templates, loopback synthetic fixture only; no production server imports.
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const { chromium } = require(process.env.MEDIFLOW_PLAYWRIGHT_MODULE || 'playwright');
const root = path.resolve(__dirname, '..');
const phase = process.argv[2];
assert.ok(['before', 'after'].includes(phase));
const base = process.env.MEDIFLOW_UI_BASE || 'http://127.0.0.1:5097';
assert.match(base, /^http:\/\/127\.0\.0\.1:\d+$/);
const out = path.join(root, 'docs/ui-redesign/typography');
const cases = [
  ['start','/',1920,1080], ['identity','/login',1920,1080],
  ['selection','/screening',1920,1080], ['survey','/screening/survey',1920,1080],
  ['capture','/capture',1920,1080], ['pending','/capture',1920,1080],
  ['result','/result',1920,1080], ['history','/report',1920,1080],
  ['operations','/admin/config',1440,900], ['research','/admin/ai-experiments',1440,900],
  ['error','/screening',1920,1080], ['modal','/login',390,844],
  ['widget','/result',390,844], ['html-report','/report/pdf',1920,1080],
  ['mobile','/screening',390,844], ['mobile-survey','/screening/survey',390,844],
  ['mobile-capture','/capture',390,844], ['mobile-result','/result',390,844],
  ['mobile-history','/report',390,844], ['mobile-pin','/m',390,844],
  ['mobile-dashboard','/m/dashboard',390,844], ['portrait','/screening/survey',1080,1920],
  ['english','/',390,844], ...['zh','vi','ru','ja'].map(n=>['language-'+n,'/',390,844]),
  ['zoom','/screening/survey',960,540], ['keyboard','/screening/survey',390,420],
  ['timeout','/capture',390,844],
  ...['m_index','m_login_start','m_survey','m_capture','m_result','m_report'].map(n=>[n,'/__fixture/template/'+n,390,844]),
  ['legacy-survey','/survey',1920,1080], ['training','/training',1920,1080],
  ['screening-capture','/screening/capture',1920,1080],
  ['screening-result','/screening/result',1920,1080], ['summary','/screening/summary',1920,1080],
];
const samples = ['MediFlow','얼굴을 화면 중앙에 맞춰주세요','촬영 준비 완료','추가 확인 권장','검사 결과를 확인해주세요','Health Screening','2026.10.07'];
(async()=>{
 fs.mkdirSync(path.join(out,'captures'),{recursive:true});
 const browser = await chromium.launch({headless:true});
 const results=[];
 try {
  for(const [name,route,width,height] of cases) {
   const context = await browser.newContext({viewport:{width,height},reducedMotion:'reduce',deviceScaleFactor:name==='zoom'?2:1, ...(name==='mobile-capture'?{userAgent:'Mozilla/5.0 iPhone Mobile'}:{})});
   const external=[], errors=[], fontRequests=[];
   await context.route('**/*',r=>{
    const u=new URL(r.request().url());
    if(u.origin===base || u.protocol==='data:')return r.continue();
    external.push(u.origin+u.pathname);
    return r.fulfill({status:200,contentType:u.pathname.endsWith('.css')?'text/css':'application/javascript',body:''});
   });
   await context.request.post(base+'/api/admin/login',{data:{password:'synthetic-admin'}});
   await context.request.post(base+'/__fixture/state',{data:{scenario:name==='error'?'config-error':'ready'}});
   const fixture=await(await context.request.get(base+'/__fixture/state')).json();
   await context.addInitScript(({f,language})=>{
    localStorage.setItem('theme','light');localStorage.setItem('i18n_language',language);
    sessionStorage.setItem('user_id','synthetic@example.invalid');sessionStorage.setItem('user_age','30');
    sessionStorage.setItem('screening_plan','["eye"]');sessionStorage.setItem('screening_active_modality','eye');
    for(const storage of [localStorage,sessionStorage]){
     storage.setItem('bilateral_capture',f.photo);storage.setItem('bilateral_analysis',JSON.stringify(f.analysis));
     storage.setItem('eye_analysis_L',JSON.stringify(f.analysis.left_eye));
    }
   },{f:fixture,language:name==='english'?'en':name.startsWith('language-')?name.slice(9):'ko'});
   const page=await context.newPage();page.setDefaultTimeout(8000);
   page.on('pageerror',e=>errors.push(e.message));
   page.on('response',r=>{if(r.url().includes('/fonts/'))fontRequests.push({path:new URL(r.url()).pathname,status:r.status()})});
   let releaseAnalysis;
   if(name==='pending')await page.route('**/analyze',async r=>{await new Promise(resolve=>releaseAnalysis=resolve);try{await r.continue()}catch{}});
   await page.goto(base+route,{waitUntil:'load'});
   await page.evaluate(()=>document.fonts.ready);await page.waitForTimeout(550);
   if(name==='modal'){await page.locator('#identifier').fill('synthetic@example.invalid');await page.locator('[type="submit"]').click();await page.locator('#confirm-toast.show').waitFor()}
   if(name==='widget'){await page.locator('.ai-chat-fab').click();await page.waitForTimeout(250)}
   if(name==='timeout')await page.locator('#screensaver-overlay').evaluate(e=>e.style.display='flex');
   if(name==='pending'){
    const image=await(await context.request.get(base+'/__fixture/image.png')).body();
    await page.locator('#upload-image-input').setInputFiles({name:'synthetic.png',mimeType:'image/png',buffer:image});
    await page.waitForTimeout(300);
   }
   if(name==='zoom'||name==='keyboard'){
    // 1920x1080 at browser 200% has a 960x540 CSS viewport.
    await page.locator('#eye-notes').fill('긴 합성 문진 안내 Health Screening synthetic@example.invalid https://example.invalid/long-identifier '.repeat(20));
    await page.locator('#submit-button').focus();
   }
   const metrics=await page.evaluate(()=>{
    const style=getComputedStyle(document.body);
    const controls=[...document.querySelectorAll('input:not([type=checkbox]):not([type=radio]):not([type=range]):not([type=file]),select:not([multiple]):not([size])')].filter(e=>e.getBoundingClientRect().width>0).map(e=>({tag:e.tagName,id:e.id,height:e.getBoundingClientRect().height,font:getComputedStyle(e).fontFamily,lineHeight:getComputedStyle(e).lineHeight}));
    const wrongFonts=[...document.querySelectorAll('body *')].filter(e=>e.children.length===0 && e.textContent.trim() && e.getBoundingClientRect().width>0 && !['SCRIPT','STYLE','CODE','PRE'].includes(e.tagName)).map(e=>({tag:e.tagName,text:e.textContent.trim().slice(0,50),font:getComputedStyle(e).fontFamily})).filter(e=>!e.font.includes('SUIT') && !e.font.includes('monospace') && !e.text.startsWith('UI DEMO'));
    const clipped=[...document.querySelectorAll('button,input,select')].filter(e=>e.getBoundingClientRect().width>0 && e.scrollHeight>e.clientHeight+2 && !e.matches('input[type=checkbox],input[type=radio],input[type=range],input[type=file]')).map(e=>({id:e.id,tag:e.tagName,height:e.clientHeight,scroll:e.scrollHeight,text:e.textContent.slice(0,70)}));
    return {bodyFont:style.fontFamily,fontSize:style.fontSize,lineHeight:style.lineHeight,letterSpacing:style.letterSpacing,width:document.documentElement.clientWidth,scrollWidth:document.documentElement.scrollWidth,controls,wrongFonts,clipped,faces:[...document.fonts].map(f=>({family:f.family,weight:f.weight,status:f.status})),checks:[400,500,600,700].map(w=>document.fonts.check(`${w} 20px "SUIT Variable"`,'얼굴 MediFlow 2026'))};
   });
   const rendered=[];
   if(phase==='after'){
    const cdp=await context.newCDPSession(page);await cdp.send('DOM.enable');await cdp.send('CSS.enable');
    const doc=await cdp.send('DOM.getDocument');
    for(const selector of ['.mf-brand','h1','button','label','input','select','.ai-chat-title','.modality p']){
     const {nodeId}=await cdp.send('DOM.querySelector',{nodeId:doc.root.nodeId,selector});
     if(nodeId)rendered.push({selector,...await cdp.send('CSS.getPlatformFontsForNode',{nodeId})});
    }
   }
   const filename=phase+'-'+name+'.png';
   await page.screenshot({path:path.join(out,'captures',filename),fullPage:true});
   if(name==='html-report' && phase==='after')fs.writeFileSync('/private/tmp/mediflow-suit-browser.pdf',await page.pdf({format:'A4',printBackground:true}));
   if(name==='start'){
    // Test-only specimens; never replace production wording.
    await page.evaluate(ss=>{
     const card=document.createElement('section');card.id='typography-specimen';card.style.cssText='padding:32px;max-width:900px;background:var(--mf-surface);margin:24px auto';
     for(const [i,text] of ss.entries()){const e=document.createElement(i===0?'h1':'p');e.id='specimen-'+i;e.textContent=text;card.appendChild(e)}document.body.appendChild(card);
    },samples);
    await page.evaluate(()=>document.fonts.ready);
    if(phase==='after'){
     const cdp=await context.newCDPSession(page);await cdp.send('DOM.enable');await cdp.send('CSS.enable');const doc=await cdp.send('DOM.getDocument');
     for(let i=0;i<samples.length;i++){
      const {nodeId}=await cdp.send('DOM.querySelector',{nodeId:doc.root.nodeId,selector:'#specimen-'+i});
      const fonts=await cdp.send('CSS.getPlatformFontsForNode',{nodeId});rendered.push({sample:samples[i],...fonts});
      assert.ok(fonts.fonts.some(f=>f.isCustomFont && f.familyName.includes('SUIT')),samples[i]);
     }
    }
    await page.locator('#typography-specimen').screenshot({path:path.join(out,'captures',phase+'-specimen.png')});
   }
   const failures=[];
   if(errors.length)failures.push('page errors');
   if(metrics.scrollWidth>metrics.width+2)failures.push('horizontal overflow');
   if(phase==='after'){
    if(!metrics.bodyFont.startsWith('"SUIT Variable"'))failures.push('body font priority');
    if(!metrics.faces.some(f=>f.family==='SUIT Variable'&&f.status==='loaded') || !metrics.checks.every(Boolean))failures.push('FontFaceSet');
    if(!fontRequests.some(r=>r.status===200&&r.path.endsWith('.woff2')))failures.push('font request');
    if(metrics.wrongFonts.length)failures.push('UI font override');
    if(metrics.clipped.length)failures.push('control text clipped');
    const expectedHeight=route.startsWith('/admin/')?44:56;
    if(metrics.controls.some(c=>Math.abs(c.height-expectedHeight)>1))failures.push('input/select height');
   }
   results.push({name,phase,route,viewport:{width,height},fixture:'mediflow-ui-v1',status:failures.length?'FAIL':'PASS',failures,errors,externalBlocked:external,fontRequests,metrics,rendered,file:filename,source:process.env.MEDIFLOW_CAPTURE_SHA||'working-tree'});
   if(releaseAnalysis)releaseAnalysis();
   await context.close();console.log(name+': '+results.at(-1).status);
  }
 }finally{await browser.close()}
 fs.writeFileSync(path.join(out,phase+'-browser.json'),JSON.stringify(results,null,2));
 const manifest=results.map(r=>({filename:r.file,repo:'Phjrab/mediflow-kiosk-core',source:r.source,captured_at:new Date().toISOString(),viewport:r.viewport,route:r.route,scenario:r.name,fixture_id:r.fixture,data_provenance:'generated shapes + deterministic synthetic JSON',live_actions:'none; loopback fixture',privacy_review:'synthetic only',sha256:crypto.createHash('sha256').update(fs.readFileSync(path.join(out,'captures',r.file))).digest('hex')}));
 const specimen=phase+'-specimen.png';
 manifest.push({...manifest[0],filename:specimen,scenario:'test-only typography specimens',sha256:crypto.createHash('sha256').update(fs.readFileSync(path.join(out,'captures',specimen))).digest('hex')});
 fs.writeFileSync(path.join(out,phase+'-manifest.json'),JSON.stringify(manifest,null,2));
 if(results.some(r=>r.status==='FAIL'))process.exitCode=1;
})().catch(e=>{console.error(e);process.exit(1)});
