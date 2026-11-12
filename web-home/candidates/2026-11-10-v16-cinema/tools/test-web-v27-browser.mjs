/* V27: real Chromium UI acceptance on the actual assembled NOX WEB.
 * No mocks, silent API calls, backend claims, OneHost restarts or fake GPU.
 */
import {chromium} from 'playwright';
import assert from 'node:assert/strict';
const base=process.env.NOX_PREVIEW_URL||'http://127.0.0.1:8080/index.html';
const browser=await chromium.launch({headless:true,args:['--use-gl=angle','--use-angle=swiftshader','--enable-webgl','--ignore-gpu-blocklist']});
const evidence=[];
try{
 for(const viewport of [{width:390,height:844},{width:1440,height:900}]){
  const page=await browser.newPage({viewport,serviceWorkers:'block',acceptDownloads:false});
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  const response=await page.goto(new URL('settings.html',base).href,{waitUntil:'domcontentloaded',timeout:60000});
  assert.equal(response?.status(),200,'Settings must be a real existing NOX page');
  await page.waitForFunction(()=>!!window.NoxFunctionCatalog&&!!window.NOX_UNIVERSE_V19,{timeout:30000});
  assert.equal((await page.evaluate(()=>window.NoxFunctionCatalog.entries.length)),36,'Original 36 catalog routes lost');
  await page.locator('#noxPublicFunctionOpen').click();
  for(const id of ['session','events']){
   const card=page.locator('.nox-function-card[data-function-id="'+id+'"]');
   assert.equal(await card.count(),1,id+' disappeared instead of truthful HOLD');
   assert.equal(await card.isDisabled(),true,id+' claims native OneHost ability on public WEB');
   assert.equal(await card.getAttribute('data-availability'),'HOLD_NATIVE_ONLY');
  }
  await page.locator('.nox-function-favorite[data-favorite-id="voice"]').click();
  assert.equal(await page.locator('.nox-function-favorite[data-favorite-id="voice"]').getAttribute('aria-pressed'),'true');
  await page.locator('.nox-function-card[data-function-id="favorites"]').click();
  const scope=await page.evaluate(()=>window.NoxFunctionCatalog.diagnostics());
  assert.equal(scope.mode,'saved','Favorites action must display real saved view');
  assert.equal(scope.favorites,1,'Saved route metadata missing');
  assert.equal(await page.locator('.nox-function-card[data-function-id="voice"]').count(),1);
  assert.equal(await page.locator('.nox-function-card[data-function-id="session"]').count(),0,'Native-only route leaked into saved UI');
  await page.locator('.nox-function-filter').click();
  assert.equal(await page.locator('.nox-function-card').count(),36,'Show all must restore full existing catalog');
  await page.locator('.nox-function-card[data-function-id="commands"]').click();
  assert.equal(await page.locator('dialog#noxFunctionCatalog[open]').count(),1,'Existing public command search must remain usable');
  assert.equal(await page.locator('#noxFunctionCatalogSearch').evaluate(n=>n===document.activeElement),true,'Commands must focus the real search');
  await page.locator('.nox-function-card[data-function-id="fx"]').click();
  await page.waitForFunction(()=>{const n=document.querySelector('.nox-v19-panel');return !!n&&!n.hidden},{timeout:10000});
  const label=await page.evaluate(()=>document.querySelector('.nox-v19-tabs button[aria-pressed="true"]')?.textContent);
  assert.equal(label,'Валюта','Existing currency module must open, not a dead route');
  await page.evaluate(()=>window.NOX_UNIVERSE_V19.close());
  await page.locator('#noxPublicFunctionOpen').click();
  await page.locator('.nox-function-card[data-function-id="favorites"]').click();
  assert.equal(await page.locator('.nox-function-card[data-function-id="fx"]').count(),1,'Real recent currency navigation not recorded');
  assert.equal(await page.locator('.nox-function-card[data-function-id="voice"]').count(),1,'Route favorite was lost after module visit');
  await page.keyboard.press('Escape');
  await page.reload({waitUntil:'domcontentloaded',timeout:60000});
  await page.waitForFunction(()=>!!window.NoxFunctionCatalog,{timeout:30000});
  await page.locator('#noxPublicFunctionOpen').click();
  assert.equal(await page.locator('.nox-function-favorite[data-favorite-id="voice"]').getAttribute('aria-pressed'),'true','Favorites did not persist after browser reload');
  assert.deepEqual(errors,[],'Unexpected uncaught JS errors in original pages');
  evidence.push({viewport:viewport.width,routes:36,publicNativeHolds:2,localFavorites:'PERSISTED',recent:'PERSISTED',currency:'EXISTING_MODULE'});
  await page.close();
 }
 console.log('NOX_WEB_V27_REAL_BROWSER_NAVIGATION_PASS',JSON.stringify(evidence));
}finally{await browser.close()}
