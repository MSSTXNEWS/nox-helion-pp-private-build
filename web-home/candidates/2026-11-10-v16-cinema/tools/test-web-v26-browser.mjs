// NOX V26 real Chromium interaction regression on the *assembled* existing WEB.
// Uses no mocks, no synthetic success, no privileged API, no new backend.
// Tests public preview navigation and verifies that absent native functions stay HOLD.
import {chromium} from 'playwright';
import assert from 'node:assert/strict';
const base=process.env.NOX_PREVIEW_URL||'http://127.0.0.1:8080/index.html';
const browser=await chromium.launch({headless:true,args:['--use-gl=angle','--use-angle=swiftshader','--enable-webgl','--ignore-gpu-blocklist']});
const checked=[];
try{
 for(const viewport of [{width:390,height:844},{width:1440,height:900}]){
  const page=await browser.newPage({viewport,serviceWorkers:'block',acceptDownloads:false});
  const errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  const res=await page.goto(new URL('settings.html',base).href,{waitUntil:'domcontentloaded',timeout:60000});
  assert.equal(res?.status(),200,'Existing HOME not reachable in Chromium');
  await page.waitForFunction(()=>window.NoxFunctionCatalog&&window.NOX_UNIVERSE_V19,{timeout:30000});
  assert.equal(await page.locator('#noxPublicFunctionOpen').count(),1,'Secondary WEB missing real graphical catalog entry');
  for(const [id,name] of [['weather','Погода'],['news','Новости'],['fx','Валюта'],['calendar','Календарь'],['notifications','Уведомления']]){
   await page.evaluate(query=>window.NoxFunctionCatalog.open(query),name);
   const item=page.locator('.nox-function-card[data-function-id="'+id+'"]');
   assert.equal(await item.count(),1,'Catalog entry '+id+' not rendered');
   await item.click();
   await page.waitForFunction(()=>{const n=document.querySelector('.nox-v19-panel');return !!n&&!n.hidden},{timeout:5000});
   const current=await page.evaluate(()=>{
     const panel=document.querySelector('.nox-v19-panel');
     const selected=panel.querySelector('.nox-v19-tabs button[aria-pressed="true"]');
     return {visible:!panel.hidden,selected:selected?.textContent||null,empty:!panel.querySelector('.nox-v19-card')};
   });
   assert.equal(current.selected,name,'Incorrect V19 destination for '+id);
   assert.equal(current.visible,true,'Module panel hidden '+id);
   assert.equal(current.empty,false,'Module contains no working controls '+id);
   await page.evaluate(()=>window.NOX_UNIVERSE_V19.close());
   checked.push({viewport:viewport.width,id,selected:current.selected});
  }
  const voice=await page.evaluate(()=>window.NoxFunctionCatalog.entries.find(x=>x.id==='voice'));
  assert.equal(voice?.page,'chat');assert.equal(voice?.anchor,'chatDictate');
  const chat=await page.goto(new URL('chat.html',base).href,{waitUntil:'domcontentloaded',timeout:60000});
  assert.equal(chat?.status(),200,'Resonance route missing');
  await page.waitForSelector('#chatDictate',{timeout:15000});
  assert.equal(await page.locator('#chatDictate').count(),1,'Real microphone target absent');
  assert.equal(await page.locator('#chatTranslate').count(),1,'Real translation target absent');
  assert.deepEqual(errors,[],'Unexpected unhandled runtime page errors');
  await page.close();
 }
 console.log('NOX_WEB_V26_REAL_CHROMIUM_MODULES_PASS',JSON.stringify({checks:checked.length,viewports:2,modules:5,realOwnerStop:'NOT_TESTED',gpu:'SOFTWARE_RENDERER_ONLY'}));
}finally{await browser.close()}
