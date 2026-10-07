const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');
const crypto=require('node:crypto');
const {chromium}=require(process.env.MEDIFLOW_PLAYWRIGHT_MODULE||'playwright');
const base='http://127.0.0.1:5108';
const out=__dirname;
(async()=>{
 const browser=await chromium.launch({headless:true});const results=[];
 try{
  for(const [name,route,width,height] of [['start','/',1920,1080],['mobile','/',390,844],['selection','/screening',1920,1080],['identity','/login',390,844]]){
   const context=await browser.newContext({viewport:{width,height},reducedMotion:'reduce'});
   const prevented=[];const fonts=[];const errors=[];
   await context.route('**/*',r=>{
    const u=new URL(r.request().url());
    if(u.protocol==='data:')return r.continue();
    if(u.origin!==base||r.request().method()!=='GET'||/\/camera|\/video|\/analyze|\/api\/(history|survey|chat)|\/report/.test(u.pathname)){
     prevented.push({path:u.pathname,method:r.request().method()});
     return r.fulfill({status:403,contentType:'application/json',body:'{"status":"error","error_code":"read_only_deploy_probe"}'});
    }
    return r.continue();
   });
   await context.addInitScript(()=>{localStorage.setItem('theme','light');localStorage.setItem('i18n_language','ko')});
   const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
   page.on('response',r=>{if(r.url().endsWith('.woff2'))fonts.push({path:new URL(r.url()).pathname,status:r.status()})});
   const response=await page.goto(base+route,{waitUntil:'load'});assert.equal(response.status(),200);
   assert.equal(response.headers()['x-mediflow-fixture'],undefined);
   await page.evaluate(()=>document.fonts.ready);await page.waitForTimeout(500);
   if(name==='selection'){
    await page.locator('[data-modality="skin"]').waitFor();
    assert.equal(await page.locator('[data-modality="skin"]').isDisabled(),true);
    assert.equal(await page.locator('[data-modality="scalp"]').isDisabled(),true);
   }
   const metrics=await page.evaluate(()=>({font:getComputedStyle(document.body).fontFamily,faces:[...document.fonts].map(f=>({family:f.family,weight:f.weight,status:f.status})),width:document.documentElement.clientWidth,scroll:document.documentElement.scrollWidth}));
   assert.ok(metrics.font.startsWith('"SUIT Variable"'));assert.ok(metrics.faces.some(f=>f.family==='SUIT Variable'&&f.status==='loaded'));assert.ok(metrics.scroll<=metrics.width+2);assert.ok(fonts.some(f=>f.status===200));
   const cdp=await context.newCDPSession(page);await cdp.send('DOM.enable');await cdp.send('CSS.enable');const doc=await cdp.send('DOM.getDocument');const rendered=[];
   for(const selector of ['.mf-brand','h1,h2']){
    const {nodeId}=await cdp.send('DOM.querySelector',{nodeId:doc.root.nodeId,selector});const face=await cdp.send('CSS.getPlatformFontsForNode',{nodeId});
    assert.ok(face.fonts.some(f=>f.isCustomFont&&f.familyName.includes('SUIT')));rendered.push({selector,...face});
   }
   assert.deepEqual(errors,[]);
   const filename='live-'+name+'.png';await page.screenshot({path:path.join(out,filename),fullPage:true});
   results.push({name,route,viewport:{width,height},status:'PASS',metrics,fonts,rendered,prevented,errors,file:filename,data:'public empty UI; no patient or identifier entered',deployment:'4b87d9e6a1a763a4117499f6cea34fb3453ae1c3'});
   await context.close();
  }
  const context=await browser.newContext();
  const admin=[];
  for(const route of ['/admin/config','/admin/ai-experiments']){
   const response=await context.request.get(base+route,{maxRedirects:0});
   assert.equal(response.status(),302);assert.equal(response.headers().location,'/login');
   admin.push({route,status:302,location:'/login'});
  }
  for(const route of ['/api/admin/config','/api/admin/ai-experiments/capabilities']){
   const response=await context.request.get(base+route);assert.equal(response.status(),403);admin.push({route,status:403});
  }
  const font=await context.request.get(base+'/static/fonts/suit/SUIT-Variable.woff2');assert.equal(font.status(),200);
  const sha=crypto.createHash('sha256').update(await font.body()).digest('hex');assert.equal(sha,'aa894a204d5a6fbae259dac6868d350cbd373a390caee0313f92946af741df23');
  results.push({name:'auth-and-font-asset',status:'PASS',anonymousAdmin:admin,fontHTTP:200,fontSHA256:sha});
  await context.close();
 }finally{await browser.close()}
 fs.writeFileSync(path.join(out,'live-smoke.json'),JSON.stringify(results,null,2));console.log(results.map(r=>r.name+' '+r.status).join('\n'));
})().catch(e=>{console.error(e);process.exit(1)});
