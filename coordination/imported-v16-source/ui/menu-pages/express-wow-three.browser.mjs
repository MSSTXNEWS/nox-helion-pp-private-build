import { chromium } from 'playwright';
import assert from 'node:assert/strict';
const browser=await chromium.launch({headless:true,channel:process.env.NOX_BROWSER_CHANNEL||undefined,executablePath:process.env.NOX_CHROME_PATH||undefined,args:['--use-gl=angle','--use-angle=swiftshader','--enable-webgl','--ignore-gpu-blocklist']});
try{
 const viewports=[[320,700],[390,844],[800,480],[1024,768],[1280,720],[1920,1080],[3840,2160]];
 for(const [width,height] of viewports){
  const page=await browser.newPage({viewport:{width,height},reducedMotion:'no-preference'});
  const pageErrors=[];page.on('pageerror',error=>pageErrors.push(String(error)));
  const errors=[];
  page.on('console',message=>{if(message.type()==='error')errors.push(message.text());});
  page.on('response',response=>{if(response.status()>=400)errors.push(response.status()+' '+response.url());});
  await page.goto('http://127.0.0.1:8765/ui/menu-pages/index.html',{waitUntil:'load'});
  try{
   await page.waitForFunction(()=>document.querySelectorAll('#directions button').length===8,null,{timeout:15000});
   await page.locator('#fx').click();
   await page.waitForFunction(()=>document.body.dataset.fx==='MAX',null,{timeout:15000});
  }catch(error){
   const diagnostic=await page.evaluate(()=>({url:location.href,fx:document.body.dataset.fx,ready:document.readyState,buttons:document.querySelectorAll('#directions button').length,status:document.querySelector('#status')?.textContent}));
   console.error('WINDOWS_EDGE_DIAGNOSTIC',JSON.stringify({width,diagnostic,errors,pageErrors}));
   await page.screenshot({path:`wow-three-windows-diagnostic-${width}.png`,fullPage:true});
   throw error;
  }
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
  assert.equal(await aetherCard.evaluate(el=>el.classList.contains('nox-tabler-card')),true,'Tabler original card pattern must mount in real route');
  const tablerBorder=await aetherCard.evaluate(el=>getComputedStyle(el).borderTopStyle);
  assert.equal(tablerBorder,'solid','Tabler bounded card style must be active');
  const glass=await aetherCard.evaluate(el=>getComputedStyle(el).backdropFilter);
  if(width>520) assert.match(glass,/blur/,'AETHER glass should be active in MAX');
  if([390,800,1920].includes(width))await page.screenshot({path:`wow-three-${width}.png`,fullPage:true});
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
  const gaugeTruth=await page.evaluate(()=>{
    const lib=window.NOXNativeGauge;
    if(typeof window.Gauge!=='function'||!lib)return {loaded:false};
    const section=document.createElement('section');document.body.append(section);
    const accepted=lib.mount(section,'gpu_usage_percent',42);
    const rejectedA=lib.mount(section,'gpu_usage_percent',-1);
    const rejectedB=lib.mount(section,'memory_gb',42);
    const rejectedC=lib.mount(section,'cpu_utilization',null);
    const realSVG=section.querySelector('svg')!==null;
    const count=section.querySelectorAll('.nox-native-svg-gauge').length;
    section.remove();
    return {loaded:true,accepted,rejectedA,rejectedB,rejectedC,realSVG,count};
  });
  assert.deepEqual(gaugeTruth,{loaded:true,accepted:true,rejectedA:false,rejectedB:false,rejectedC:false,realSVG:true,count:1});
  assert.equal(await page.locator('.nox-native-svg-gauge').count(),0,'Never display telemetry without authenticated native receipt');
  await page.waitForFunction(()=>document.querySelector('.core-section')?.dataset.noxZodiac==='active');
  assert.equal(await page.locator('.nox-zodiac-lines circle').count(),8,'ZODIAC must connect exactly eight original CoreID nodes');
  assert.equal(await page.locator('#cores button.core').count(),8,'ZODIAC cannot duplicate native CoreID buttons');
  const buttons=await page.locator('#directions button').count();
  assert.equal(buttons,8,'All eight original navigation directions remain');

  const geometry=await page.evaluate(()=>{
   const actions=[...document.querySelectorAll('#actions button')];
   const cores=[...document.querySelectorAll('#cores button')];
   return {viewport:innerWidth,scrollWidth:document.documentElement.scrollWidth,
     actions:actions.length,cores:cores.length,
     maxButtonWidth:Math.max(...actions.map(x=>x.getBoundingClientRect().width),0),
     allVisible:[...actions,...cores].every(x=>{const r=x.getBoundingClientRect();return r.width>=20&&r.height>=20;})};
  });
  if(geometry.scrollWidth>geometry.viewport+2){
   const leaking=await page.evaluate(()=>[...document.querySelectorAll('body *')].map(el=>{
    const r=el.getBoundingClientRect();
    return {tag:el.tagName.toLowerCase(),id:el.id,className:typeof el.className==='string'?el.className.slice(0,90):'',left:Math.round(r.left),right:Math.round(r.right),width:Math.round(r.width)};
   }).filter(r=>r.right>innerWidth+2||r.left< -2).sort((a,b)=>b.right-a.right).slice(0,20));
   console.error('NOX_WOW_OVERFLOW_ELEMENTS',width,JSON.stringify(leaking));
   const containers=await page.evaluate(()=>[...document.querySelectorAll('html,body,body *')].filter(el=>el.scrollWidth>el.clientWidth+3).map(el=>{
    const b=el.getBoundingClientRect();return {tag:el.tagName,id:el.id,className:typeof el.className==='string'?el.className.slice(0,70):'',scrollWidth:el.scrollWidth,clientWidth:el.clientWidth,right:Math.round(b.right)};
   }).slice(0,30));
   console.error('NOX_WOW_OVERFLOW_CONTAINERS',width,JSON.stringify(containers));
  }
  assert.equal(geometry.scrollWidth<=geometry.viewport+2,true,`Horizontal overflow at ${width}x${height}: ${JSON.stringify(geometry)}`);
  assert.equal(geometry.actions,5,'Five source-defined main actions remain');
  assert.equal(geometry.cores,8,'Eight CoreID buttons remain');
  assert.equal(geometry.allVisible,true,'Original action/CoreID controls retain usable hitboxes');
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
 console.log('PASS: real Chromium HALO + HELIODON + AETHER + SVG Gauge + WebGL MAX/ECO, seven viewports including 320/390/800x480/4K, nav, Reduced Motion');
} finally {await browser.close();}
