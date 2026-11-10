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
  let status=null,snapshot=null,assetCheck=null,blocked=null;
  try{
   const response=await page.goto(url,{waitUntil:'domcontentloaded',timeout:45000});
   status=response?.status()||null;
   await page.waitForTimeout(5000);
   blocked=await page.evaluate(()=>/authentication|log in|sign in/i.test(document.title)&&!document.querySelector('.helion-stage'));
   snapshot=await page.evaluate(()=>window.NOX_CINEMATIC_HEALTH?.snapshot?.()||null);
   if(name==='1440' && snapshot) assetCheck=await page.evaluate(()=>window.NOX_CINEMATIC_HEALTH.checkAssets().catch(e=>({error:String(e)})));
   await page.screenshot({path:path.join(out,name+'.png'),fullPage:true,timeout:30000});
  }catch(e){errors.push('RUN: '+String(e.message||e))}
  const acceptance=blocked?'BLOCKED_SSO':!snapshot?'HOLD_NO_RUNTIME_DIAGNOSTICS':snapshot.graphicsAcceptance==='CANDIDATE'&&errors.length===0?'BROWSER_CANDIDATE':'HOLD';
  report.cases.push({viewport:name,width,height,httpStatus:status,acceptance,blocked,diagnostics:snapshot,assetCheck,errors});
  await page.close();
 }
}finally{await browser.close()}
report.completedAt=new Date().toISOString();
report.summary={browserCandidates:report.cases.filter(c=>c.acceptance==='BROWSER_CANDIDATE').length,total:report.cases.length,physicalGpu:'NOT_TESTED'};
await fs.writeFile(path.join(out,'report.json'),JSON.stringify(report,null,2));
console.log(JSON.stringify(report.summary));
if(report.summary.browserCandidates!==viewports.length || report.cases.some(c=>c.assetCheck && c.assetCheck.passed!==14))process.exitCode=1;
