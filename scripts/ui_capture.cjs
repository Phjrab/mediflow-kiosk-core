#!/usr/bin/env node
// Run against scripts/ui_preview.py only. Playwright is an optional dev tool.
const fs = require('node:fs');
const path = require('node:path');
const {execFileSync} = require('node:child_process');
const {chromium} = require(process.env.MEDIFLOW_PLAYWRIGHT_MODULE || 'playwright');
const root = path.resolve(__dirname, '..');
const base = process.env.MEDIFLOW_UI_BASE || 'http://127.0.0.1:5097';
if (!/^http:\/\/127\.0\.0\.1:\d+$/.test(base)) throw new Error('Only explicit loopback preview allowed');
const phase = process.argv[2] || 'after';
const out = path.join(root, 'docs/ui-redesign/captures');
const cases = [
  ['start', '/', 1920, 1080], ['selection', '/screening', 1920, 1080],
  ['survey', '/screening/survey', 1366, 768], ['capture', '/capture', 1920, 1080],
  ['result', '/result', 1920, 1080], ['operations', '/admin/config', 1366, 768],
  ['research', '/admin/ai-experiments', 1366, 768], ['mobile', '/screening', 390, 844],
  ['history', '/report', 1024, 768],
];
function csv(value) {return '"' + String(value).replaceAll('"', '""') + '"';}
(async () => {
  fs.mkdirSync(out, {recursive:true});
  const browser = await chromium.launch({headless:true});
  const log = [];
  try {
    for (const [name, route, width, height] of cases) {
      const context = await browser.newContext({viewport:{width,height}, reducedMotion:'reduce'});
      const events = {errors:[], externalBlocked:[], requests:[]};
      await context.route('**/*', async r => {
        const u = new URL(r.request().url());
        if (u.protocol === 'data:' || u.origin === base) return r.continue();
        events.externalBlocked.push(u.origin + u.pathname);
        return r.fulfill({status:200, contentType: u.pathname.endsWith('.css') ? 'text/css' : 'application/javascript', body:''});
      });
      const page = await context.newPage();
      page.on('pageerror', e=>events.errors.push(e.message));
      page.on('console', m=>{if(m.type()==='error') events.errors.push(m.text())});
      page.on('request', r=>{if(r.url().startsWith(base)) events.requests.push({url:r.url().replace(base,''),method:r.method()})});
      // Authentication is against the fixture adapter only.
      await context.request.post(base+'/api/admin/login',{data:{password:'synthetic-admin'}});
      const fixture = await (await context.request.get(base+'/__fixture/state')).json();
      await context.addInitScript(f=>{
        localStorage.setItem('theme','light'); localStorage.setItem('i18n_language','ko');
        sessionStorage.setItem('user_id','synthetic@example.invalid');
        sessionStorage.setItem('user_age','30');
        sessionStorage.setItem('screening_plan','["eye"]');
        sessionStorage.setItem('screening_active_modality','eye');
        for(const storage of [localStorage,sessionStorage]) {
          storage.setItem('bilateral_capture',f.photo);
          storage.setItem('bilateral_analysis',JSON.stringify(f.analysis));
          storage.setItem('eye_analysis_L',JSON.stringify(f.analysis.left_eye));
        }
      },fixture);
      await page.goto(base+route,{waitUntil:'load'});
      await page.evaluate(()=>document.fonts.ready);
      await page.waitForTimeout(700); // allow existing i18n's 300ms pass and API rendering
      await page.addStyleTag({content:'*,*::before,*::after {animation:none !important;transition:none !important}'});
      if(name==='survey') await page.locator('#age').fill('30');
      const filename=phase+'-'+name+'.png';
      await page.screenshot({path:path.join(out,filename),fullPage:true});
      const sha=process.env.MEDIFLOW_CAPTURE_SHA || execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim();
      const row=[filename,'Phjrab/mediflow-kiosk-core',sha,new Date().toISOString(),width+'x'+height,route,name,'mediflow-ui-v1','generated shapes + deterministic synthetic JSON','none; fixture adapter only','synthetic reviewed'];
      const manifest=path.join(out,'CAPTURE_MANIFEST.csv');
      if(!fs.existsSync(manifest)) fs.writeFileSync(manifest,'filename,repo,commit_sha,captured_at,viewport,route,scenario,fixture_id,data_provenance,live_actions,privacy_review\n');
      const existing=fs.readFileSync(manifest,'utf8').split('\n').filter(line=>line && !line.startsWith(csv(filename)+','));
      fs.writeFileSync(manifest,existing.join('\n')+'\n'+row.map(csv).join(',')+'\n');
      log.push({name,phase,viewport:{width,height},...events});
      await context.close();
    }
  } finally {await browser.close();}
  fs.writeFileSync(path.join(root,'docs/ui-redesign/logs',phase+'-browser.json'),JSON.stringify(log,null,2));
  console.log(JSON.stringify(log.map(x=>({name:x.name,errors:x.errors,externalBlocked:x.externalBlocked.length})),null,2));
})().catch(e=>{console.error(e);process.exit(1)});
