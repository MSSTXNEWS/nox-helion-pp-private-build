import { chromium } from 'playwright';
import assert from 'node:assert/strict';
const browser=await chromium.launch({headless:true,args:['--use-gl=angle','--use-angle=swiftshader','--enable-webgl','--ignore-gpu-blocklist']});
try{
 for(const width of [390,800,1920]){
  const page=await browser.newPage({viewport:{width,height:900},reducedMotion:'no-preference'});
  const pageErrors=[];page.on('pageerror',error=>pageErrors.push(String(error)));
  await page.goto('http://127.0.0.1:8765/ui/menu-pages/index.html',{waitUntil:'load'});
  await page.locator('#fx').click();
  await page.waitForFunction(()=>document.body.dataset.fx==='MAX');
  const state=await page.waitForFunction(()=>{
   const stage=document.querySelector('.universe');
   return ['active','fallback'].includes(stage?.dataset.wowThreeState);
  },null,{timeout:25000}).then(()=>page.locator('.universe').getAttribute('data-wow-three-state'));
  assert.equal(state,'active',`Three WebGL MAX not active at ${width}px: ${state}`);
  assert.equal(await page.locator('canvas.nox-wow-three').isVisible(),true);
  await page.screenshot({path:`wow-three-${width}.png`,fullPage:true});
  await page.locator('#fx').click();
  await page.waitForFunction(()=>document.body.dataset.fx==='ECO');
  assert.equal(await page.locator('canvas.nox-wow-three').isVisible(),false);
  const buttons=await page.locator('#directions button').count();
  assert.equal(buttons,8,'All eight original navigation directions remain');
  assert.equal(pageErrors.length,0,pageErrors.join('; '));
  await page.close();
 }
 const reduced=await browser.newPage({viewport:{width:800,height:700},reducedMotion:'reduce'});
 await reduced.goto('http://127.0.0.1:8765/ui/menu-pages/index.html',{waitUntil:'load'});
 await reduced.locator('#fx').click();
 await reduced.waitForTimeout(400);
 assert.equal(await reduced.locator('canvas.nox-wow-three').isVisible(),false);
 await reduced.close();
 console.log('PASS: real Chromium WebGL MAX/ECO, 390/800/1920 widths, nav, Reduced Motion');
} finally {await browser.close();}
