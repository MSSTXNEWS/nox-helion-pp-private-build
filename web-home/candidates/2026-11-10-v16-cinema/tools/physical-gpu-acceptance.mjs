/* NOX V18 PHYSICAL GPU acceptance. Real Windows Edge, never SwiftShader or synthetic PASS.
 * Run on a Windows machine with a physical GPU:
 * NOX_SITE_URL=http://127.0.0.1:8080 node tools/physical-gpu-acceptance.mjs
 * Requires Playwright (npm i -D playwright) and installed Microsoft Edge.
 * Does not start/stop any NOX backend, change production or fake telemetry.
 */
import { chromium } from 'playwright';
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
const source=process.env.NOX_SITE_URL;
if(!source||!/^https?:\/\//.test(source))throw Error('NOX_SITE_URL_REQUIRED_REAL_SITE');
const out=path.resolve(process.env.NOX_GPU_QA_OUT||'./nox-physical-gpu-qa');
await fs.mkdir(out,{recursive:true});
const report={source,kind:'HARDWARE_GPU_BROWSER',startedAt:new Date().toISOString(),screenshots:[],routes:[],render:{},errors:[],acceptance:'HOLD'};
const browser=await chromium.launch({channel:'msedge',headless:false,args:['--enable-gpu','--ignore-gpu-blocklist']});
const sizes=[['320',320,720],['390',390,844],['800x480',800,480],['1024',1024,768],['1440',1440,900],['1920',1920,1080],['4k',3840,2160]];
try{
 const page=await browser.newPage({viewport:{width:1920,height:1080},deviceScaleFactor:1});
 page.on('pageerror',e=>report.errors.push('JS: '+e.message));
 page.on('console',m=>{if(m.type()==='error')report.errors.push('CONSOLE: '+m.text())});
 const response=await page.goto(new URL('index.html',source).href,{waitUntil:'domcontentloaded',timeout:60000});
 report.http=response?.status()||null;
 await page.waitForTimeout(9000);
 report.render=await page.evaluate(async()=>{
  const canvas=document.querySelector('#noxEclipseCanvas');
  const gl=canvas?.getContext('webgl2')||canvas?.getContext('webgl');
  const debug=gl?.getExtension('WEBGL_debug_renderer_info');
  const vendor=debug?gl.getParameter(debug.UNMASKED_VENDOR_WEBGL):null;
  const renderer=debug?gl.getParameter(debug.UNMASKED_RENDERER_WEBGL):null;
  const core=window.noxHomeDiagnostics?.()||null;
  const world=window.NOX_PHYSICAL_WORLDS_QA?.()||null;
  const health=window.NOX_CINEMATIC_HEALTH?.snapshot?.()||null;
  let assets=null;try{assets=await window.NOX_CINEMATIC_HEALTH?.checkAssets?.()}catch(e){assets={error:String(e)}}
  return {vendor,renderer,webglContext:!!gl,core,world,health,assets};
 });
 for(const [name,width,height] of sizes){
  await page.setViewportSize({width,height});
  await page.waitForTimeout(1200);
  const file=path.join(out,name+'.png');
  await page.screenshot({path:file,fullPage:true,timeout:40000});
  const bytes=await fs.readFile(file);report.screenshots.push({viewport:name,width,height,path:file,sha256:crypto.createHash('sha256').update(bytes).digest('hex'),bytes:bytes.length});
 }
 await page.close();
 for(const route of ['index.html','chat.html','cinema.html','install.html','memory.html','models.html','projects.html','settings.html','system.html','training.html']){
  const p=await browser.newPage({viewport:{width:1280,height:800}});
  p.on('pageerror',e=>report.errors.push(route+': '+e.message));
  let status=null,ui=null;try{const res=await p.goto(new URL(route,source).href,{waitUntil:'domcontentloaded',timeout:45000});status=res?.status()||null;await p.waitForTimeout(1200);ui=await p.evaluate(()=>({visibleSelectCount:[...document.querySelectorAll('select')].filter(x=>{const s=getComputedStyle(x),r=x.getBoundingClientRect();return s.display!=='none'&&s.visibility!=='hidden'&&Number(s.opacity)>0&&r.width>2&&r.height>2}).length,sharedLayer:!!window.NOX_WOW_GLOBAL_V18}))}catch(e){report.errors.push(route+': '+String(e))}
  report.routes.push({route,status,ui});await p.close();
 }
 const x=report.render,renderer=x.renderer||'UNREPORTED';
 const software=/swiftshader|llvmpipe|software rasterizer|microsoft basic render|warp/i.test(renderer);
 const realHardware=!!x.vendor&&!!x.renderer&&!software;
 const coreOkay=x.core?.status==='READY'&&x.core?.renderCount>15;
 const worldOkay=x.world?.count===14&&x.world?.allMaterialAssetsReady===true&&x.world?.textureFailures===0;
 const assetsOkay=x.assets?.passed===14&&x.assets?.total===14;
 const routesOkay=report.routes.length===10&&report.routes.every(y=>y.status===200&&y.ui?.visibleSelectCount===0&&y.ui?.sharedLayer);
 const layoutOkay=x.health?.graphicsAcceptance==='CANDIDATE';
 report.conditions={realHardware,coreOkay,worldOkay,assetsOkay,routesOkay,layoutOkay,noJavaScriptErrors:report.errors.length===0};
 report.acceptance=Object.values(report.conditions).every(Boolean)?'PASS':'HOLD';
}finally{report.finishedAt=new Date().toISOString();await browser.close();await fs.writeFile(path.join(out,'qa-report.json'),JSON.stringify(report,null,2))}
console.log(JSON.stringify({acceptance:report.acceptance,gpu:report.render.renderer,conditions:report.conditions,screenshots:report.screenshots.length,routes:report.routes.length}));
if(report.acceptance!=='PASS')process.exitCode=1;
