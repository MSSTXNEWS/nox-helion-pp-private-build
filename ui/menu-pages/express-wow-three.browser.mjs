import { chromium } from 'playwright';
import assert from 'node:assert/strict';
const browser=await chromium.launch({headless:true,executablePath:process.env.NOX_CHROME_PATH||undefined,args:['--use-gl=angle','--use-angle=swiftshader','--enable-webgl','--ignore-gpu-blocklist']});
try{
 for(const width of [390,800,1920]){
  const page=await browser.newPage({viewport:{width,height:900},reducedMotion:'no-preference'});
  const pageErrors=[];page.on('pageerror',error=>pageErrors.push(String(error)));
  await page.goto('http://127.0.0.1:8765/ui/menu-pages/index.html',{waitUntil:'load'});
  await page.locator('#fx').click();
  await page.waitForFunction(()=>document.body.dataset.fx==='MAX');
  await page.waitForFunction(()=>document.querySelector('.universe')?.dataset.noxHaloHud==='1');
  const halo=page.locator('canvas.nox-halo-radar');
  assert.equal(await halo.count(),1,'HALO should mount into original universe');
  assert.equal(await halo.isVisible(),true,'HALO should show in MAX');
  assert.ok(await halo.evaluate(el=>el.width>0&&el.height>0),'HALO must render real pixels');
  const state=await page.waitForFunction(()=>{
   const stage=document.querySelector('.universe');
   return ['active','fallback'].includes(stage?.dataset.wowThreeState);
  },null,{timeout:25000}).then(()=>page.locator('.universe').getAttribute('data-wow-three-state'));
  assert.equal(state,'active',`Three WebGL MAX not active at ${width}px: ${state}`);
  assert.equal(await page.locator('.universe').getAttribute('data-wow-heliodon'),'active','HELIODON metal scene should be mounted within same Three renderer');
  assert.equal(await page.locator('canvas.nox-wow-three').isVisible(),true);
  await page.locator('#directions button').first().click();
  const aetherCard=page.locator('.details .nox-catalog-card').first();
  assert.equal(await aetherCard.isVisible(),true,'AETHER must style real navigation cards');
  const glass=await aetherCard.evaluate(el=>getComputedStyle(el).backdropFilter);
  if(width>520) assert.match(glass,/blur/,'AETHER glass should be active in MAX');
  await page.screenshot({path:`wow-three-${width}.png`,fullPage:true});
  await page.locator('#fx').click();
  await page.waitForFunction(()=>document.body.dataset.fx==='ECO');
  assert.equal(await page.locator('canvas.nox-wow-three').isVisible(),false);
  assert.equal(await halo.isVisible(),false,'HALO must be hidden in ECO');
  assert.equal(await aetherCard.evaluate(el=>getComputedStyle(el).backdropFilter),'none','AETHER blur must be disabled in ECO');
  await page.waitForFunction(()=>!!customElements.get('loquix-typing-indicator'));
  const loadedLoquix=await page.evaluate(()=>{
   const element=document.createElement('loquix-typing-indicator');
   document.body.append(element);
   const shadow=!!element.shadowRoot;
   element.remove();
   return shadow;
  });
  assert.equal(loadedLoquix,true,'Original Loquix Lit Web Component must render');
  await page.locator('#actions button[data-action="CHAT"]').click();
  assert.equal(await page.locator('.nox-chat-log').count(),1,'Original native CHAT remains reachable');
  assert.equal(await page.locator('.nox-loquix-typing').count(),0,'No fake streaming indicator before native request');
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
 assert.equal(await reduced.locator('canvas.nox-halo-radar').count(),1,'HALO static fallback must exist under reduced motion');
 await reduced.close();
 console.log('PASS: real Chromium HALO + HELIODON + AETHER + WebGL MAX/ECO, 390/800/1920 widths, nav, Reduced Motion');
} finally {await browser.close();}
