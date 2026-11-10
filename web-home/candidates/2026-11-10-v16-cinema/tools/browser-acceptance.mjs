// NOX HOME V18 — real Playwright browser acceptance, never a synthetic PASS.
// Usage: NOX_PREVIEW_URL=http://127.0.0.1:8080 node tools/browser-acceptance.mjs
// Install Playwright in the runner: npm install --no-save playwright && npx playwright install chromium
// Protected Vercel previews require genuine browser authentication. A sign-in page is a HOLD, not PASS.
import { chromium } from 'playwright';
import fs from 'node:fs/promises';
import path from 'node:path';

const url = process.env.NOX_PREVIEW_URL;
if (!url || !/^https?:\/\//.test(url)) throw Error('Set NOX_PREVIEW_URL to the ACTUAL deployed candidate or locally served full site');
const out = process.env.NOX_ACCEPTANCE_DIR || './nox-v18-acceptance';
await fs.mkdir(out,{recursive:true});
const viewports = [
 ['320',320,720],['390',390,844],['800x480',800,480],
 ['1024',1024,768],['1440',1440,900],['1920',1920,1080],['4k',3840,2160]
];
const browser=await chromium.launch({headless:true,args:['--enable-webgl','--use-gl=angle','--use-angle=swiftshader']});
const report={source:url,startedAt:new Date().toISOString(),browser:'Chromium SwiftShader (not a physical GPU)',cases:[],physicalGpuAcceptance:'HOLD'};
try{
 for(const [name,width,height] of viewports){
  const page=await browser.newPage({viewport:{width,height},deviceScaleFactor:1});
  const errors=[];page.on('pageerror',e=>errors.push('JS: '+e.message));page.on('console',msg=>{if(msg.type()==='error')errors.push('CONSOLE: '+msg.text())});
  let status=null,snapshot=null,assetCheck=null,ownerCheck=null,blocked=null;
  try{
   const response=await page.goto(url,{waitUntil:'domcontentloaded',timeout:45000});
   status=response?.status()||null;
   await page.waitForTimeout(5000);
   blocked=await page.evaluate(()=>/authentication|log in|sign in/i.test(document.title)&&!document.querySelector('.helion-stage'));
   snapshot=await page.evaluate(()=>window.NOX_CINEMATIC_HEALTH?.snapshot?.()||null);
   ownerCheck=await page.evaluate(()=>{
    const cores=[...document.querySelectorAll('.nox-owner-core')],people=[...document.querySelectorAll('.nox-owner-persona')];
    const rect=e=>{const b=e.getBoundingClientRect();return {x:b.left,y:b.top,w:b.width,h:b.height}};
    const personas=people.map(p=>({name:p.textContent.trim(),size:rect(p)}));
    const rig=cores.map(c=>({name:c.textContent.trim(),href:c.getAttribute('href'),size:rect(c)}));
    return {ready:!!window.NOX_OWNER_HOME_V20,mode:document.body.dataset.noxOwnerLayout,
     cores:rig,personas,art:!!document.querySelector('link[href*="nox-owner-director-v20.css"]'),
     controlsPreserved:document.querySelectorAll('section.nox-orbital-controls button').length,
     originalWebgl:!!document.getElementById('noxEclipseCanvas'),navLinks:document.querySelectorAll('nav.home-primary-navigation a[href]').length,
     ownerButtons:document.querySelectorAll('.nox-owner-actions button').length};
   });
   if(name==='1440'){
     ownerCheck.artHttp=await page.evaluate(async()=>{
       const r=await fetch('./assets/nox-owner-approved/NOX_HOME_OWNER_APPROVED_WEB.webp',{cache:'no-store'});
       if(!r.ok)return {status:r.status,verified:false};
       const bytes=await r.arrayBuffer(),hash=await crypto.subtle.digest('SHA-256',bytes);
       const sha=[...new Uint8Array(hash)].map(x=>x.toString(16).padStart(2,'0')).join('');
       return {status:r.status,size:bytes.byteLength,sha256:sha,verified:sha==='3253d26819a70b49259fdb2a56c2eaa2455c6878cb2ccb8d62b225ec6ccdfa22'};
     });
   }
   if(name==='1440' && snapshot) assetCheck=await page.evaluate(()=>window.NOX_CINEMATIC_HEALTH.checkAssets().catch(e=>({error:String(e)})));
   await page.screenshot({path:path.join(out,name+'.png'),fullPage:true,timeout:30000});
  }catch(e){errors.push('RUN: '+String(e.message||e))}
  const acceptance=blocked?'BLOCKED_SSO':!snapshot?'HOLD_NO_RUNTIME_DIAGNOSTICS':snapshot.graphicsAcceptance==='CANDIDATE'&&errors.length===0?'BROWSER_CANDIDATE':'HOLD';
  report.cases.push({viewport:name,width,height,httpStatus:status,acceptance,blocked,diagnostics:snapshot,assetCheck,ownerCheck,errors});
  await page.close();
 }
 // Cross-section smoke checks: no fake backends, no hidden failures.
 const pages=['index.html','chat.html','cinema.html','install.html','memory.html','models.html','projects.html','settings.html','system.html','training.html'];
 report.sections=[];
 for(const name of pages){
  const page=await browser.newPage({viewport:{width:1440,height:900}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  let status=null,checks=null;
  try{
   const response=await page.goto(new URL(name,url).href,{waitUntil:'domcontentloaded',timeout:45000});
   status=response?.status()||null;
   await page.waitForTimeout(1250);
   checks=await page.evaluate(()=>{
    const select=[...document.querySelectorAll('select')];
    const visibleSelects=select.filter(el=>{const s=getComputedStyle(el),r=el.getBoundingClientRect();return s.visibility!=='hidden'&&s.display!=='none'&&s.opacity!=='0'&&r.width>1&&r.height>1});
    const buttons=[...document.querySelectorAll('button')];
    const missingLinks=[...document.querySelectorAll('a[href]')].filter(a=>!a.getAttribute('href')?.trim()).length;
    return {v19Style:!!document.querySelector('link[href*="nox-universe-v19.css"]'),v19Script:!!window.NOX_UNIVERSE_V19,sharedStyle:!!document.querySelector('link[href*="nox-global-wow-v18.css"]'),sharedScript:!!window.NOX_WOW_GLOBAL_V18,visibleSelects:visibleSelects.length,choiceGroups:document.querySelectorAll('.nox-wow-choice-group').length,buttons:buttons.length,missingLinks};
   });
  }catch(e){errors.push(String(e))}
  report.sections.push({name,status,checks,errors,acceptance:status===200&&checks?.sharedStyle&&checks?.sharedScript&&checks?.v19Style&&checks?.v19Script&&checks.visibleSelects===0&&errors.length===0?'PAGE_UI_PASS':'HOLD'});
  await page.close();
 }

 // Exercise actual V19 click-to-load controls, not just presence of JS/CSS tags.
 report.v19Modules=[];
 const p=await browser.newPage({viewport:{width:1440,height:900}});
 const moduleErrors=[];p.on('pageerror',e=>moduleErrors.push(String(e.message||e)));
 try{
  const response=await p.goto(new URL('index.html',url).href,{waitUntil:'domcontentloaded',timeout:45000});
  if(response?.status()!==200)throw Error('HOME_HTTP_'+response?.status());
  await p.waitForFunction(()=>!!window.NOX_UNIVERSE_V19,{timeout:15000});
  await p.locator('.nox-v19-launch').click();
  const moduleButtons=await p.locator('.nox-v19-tabs button').allTextContents();
  for(const name of ['Кинотеатр','Книги','Календарь','Галерея','Эффекты','Новости','Уведомления','Погода','Валюта','Браузер','Разделы'])
   if(!moduleButtons.includes(name))throw Error('NOX_V19_MISSING_MODULE_BUTTON_'+name);
  await p.getByRole('button',{name:'Календарь',exact:true}).click();
  await p.waitForSelector('.nox-v19-calendar .fc',{timeout:25000});
  await p.getByPlaceholder('Название события').fill('NOX-CI-TEST');
  await p.locator('.nox-v19-card input[type="date"]').first().fill('2026-11-11');
  await p.getByRole('button',{name:'ДОБАВИТЬ СОБЫТИЕ'}).click();
  const events=await p.evaluate(()=>JSON.parse(localStorage.getItem('nox-v19-calendar-events')||'[]'));
  report.v19Modules.push({name:'Календарь',source:'FullCalendar local',passed:events.some(e=>e.title==='NOX-CI-TEST')});
  await p.getByRole('button',{name:'Галерея',exact:true}).click();
  const tinyPng=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jzF8AAAAASUVORK5CYII=','base64');
  await p.locator('.nox-v19-card input[type=file]').first().setInputFiles({name:'test.png',mimeType:'image/png',buffer:tinyPng});
  await p.waitForSelector('.nox-v19-gallery a',{timeout:15000});
  await p.waitForFunction(()=>!!document.querySelector('link[href*="photoswipe.css"]'),{timeout:12000});
  report.v19Modules.push({name:'Галерея',source:'PhotoSwipe local',passed:await p.locator('.nox-v19-gallery a').count()===1});
  await p.getByRole('button',{name:'Эффекты',exact:true}).click();
  await p.getByRole('button',{name:'ECO · 15'}).click();
  await p.waitForFunction(()=>!!(window.tsParticles||window.__tsParticlesInternals?.engine?.tsParticles),{timeout:25000});
  await p.getByRole('button',{name:'STOP FX'}).click();
  report.v19Modules.push({name:'Эффекты',source:'tsParticles local',passed:true,physicalGpu:'NOT_TESTED'});
 }catch(e){moduleErrors.push(String(e?.message||e))}
 report.v19ModuleErrors=moduleErrors;
 await p.close();
}finally{await browser.close()}
report.completedAt=new Date().toISOString();
report.summary={browserCandidates:report.cases.filter(c=>c.acceptance==='BROWSER_CANDIDATE').length,total:report.cases.length,physicalGpu:'NOT_TESTED',v19ModulesPassed:report.v19Modules?.filter(x=>x.passed).length||0,pageUiPassed:report.sections?.filter(x=>x.acceptance==='PAGE_UI_PASS').length??0};
await fs.writeFile(path.join(out,'report.json'),JSON.stringify(report,null,2));
console.log(JSON.stringify(report.summary));
if(report.cases.some(c=>!c.ownerCheck?.ready||c.ownerCheck.cores?.length!==8||c.ownerCheck.personas?.length!==5||!c.ownerCheck.originalWebgl)||report.cases.some(c=>c.ownerCheck?.artHttp&&!c.ownerCheck.artHttp.verified)||report.summary.v19ModulesPassed!==3 || report.v19ModuleErrors?.length || report.summary.pageUiPassed!==10 || report.summary.browserCandidates!==viewports.length || report.cases.some(c=>c.assetCheck && c.assetCheck.passed!==14))process.exitCode=1;
