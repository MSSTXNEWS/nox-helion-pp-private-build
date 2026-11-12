/** Actual NOX WEB V29 merged-site interaction tests (no mocks).
 * The only expected native result on a statically hosted source preview is HOLD.
 */
import { chromium } from 'playwright';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
const origin = process.env.NOX_V29_TEST_ORIGIN;
if(!origin||!/^https:\/\/sb-[a-z0-9]+\.vercel\.run\/$/.test(origin))throw Error('NOX_V29_PREVIEW_ORIGIN_UNTRUSTED');
const screenshots = process.env.NOX_V29_SCREENSHOTS_DIR || './v29-e2e';
await fs.mkdir(screenshots,{recursive:true});
const browser = await chromium.launch({headless:true,args:['--enable-webgl','--use-gl=angle','--use-angle=swiftshader']});
const actual=[];
try {
  for(const [width,height] of [[390,844],[1440,900]]) {
    const page = await browser.newPage({viewport:{width,height},reducedMotion:'reduce'});
    const exceptions=[];
    page.on('pageerror',e=>exceptions.push(e.message));
    for(const [route,addon] of [['chat.html',true],['memory.html',true],['training.html',true],['system.html',false]]) {
      const resp=await page.goto(origin+route,{waitUntil:'domcontentloaded',timeout:60000});
      assert.equal(resp?.status(),200,route+' HTTP not 200');
      if(addon) {
        await page.waitForSelector('#nox-v29-addons',{timeout:20000});
        const n=await page.locator('[data-nox-pc-action]').count();
        assert.ok(n>=2,route+' has no real PC addon controls');
        assert.equal(await page.locator('iframe').count(),0,'Second chat UI was embedded by mistake');
        await page.locator('[data-nox-pc-action="genesis"]').click();
        await page.waitForFunction(()=>/HOLD/.test(document.querySelector('.nox-v29-result')?.textContent||''),null,{timeout:15000});
        const diag=await page.evaluate(()=>window.NOX_WEB_V29_ADDONS?.diagnostics());
        assert.equal(diag?.trustedNative,false,'Public preview falsely claimed native P02');
        assert.equal(diag?.liveGpuAccepted,false,'Preview falsely claimed hardware GPU');
        assert.match(await page.locator('.nox-v29-result').innerText(),/HOLD/);
      } else {
        const anchor=page.getByRole('link',{name:'МОНИТОРИНГ',exact:true});
        assert.equal(await anchor.getAttribute('href'),'system.html#dashboard-overview');
        await anchor.click();
        assert.match(page.url(),/system\.html#dashboard-overview$/);
      }
      actual.push({width,route,status:200,addon:addon?'VISIBLE_AND_HOLD':'ROUTE_FIXED'});
    }
    for(const route of ['pc/resonance.html','pc/memory.html','pc/chat.html']) {
      const r=await page.goto(origin+route,{waitUntil:'domcontentloaded',timeout:60000});
      assert.equal(r?.status(),200,route+' missing');
      if(route==='pc/resonance.html'||route==='pc/memory.html'){
        const back=page.locator('.nox-v28-pc-return a');
        assert.equal(await back.count(),1,route+' missing return to canonical pages');
        const target=await back.getAttribute('href');
        assert.ok(['../chat.html','../memory.html'].includes(target),'unsafe PC return path');
      }
      actual.push({width,route,status:200});
    }
    if(width===1440){
      const r=await page.goto(origin+'index.html',{waitUntil:'domcontentloaded',timeout:60000});
      assert.equal(r?.status(),200);
      await page.waitForSelector('.nox-owner-core',{timeout:30000});
      assert.equal(await page.locator('.nox-owner-core').count(),8,'Original D02 eight CoreIDs lost');
      assert.equal(await page.locator('.nox-owner-persona').count(),5,'Approved five Persona lost');
      assert.equal(await page.locator('section.nox-orbital-controls button').count(),14,'Original 14 world controls lost');
      assert.equal(await page.locator('#nox-v29-addons').count(),0,'Addons rendered over owner HOME');
      const d=await page.evaluate(()=>({worlds:window.NOX_CINEMATIC_HEALTH?.snapshot?.()?.worlds||null,core:window.NOX_CINEMATIC_HEALTH?.snapshot?.()?.core||null}));
      assert.ok(d.worlds,'Original PBR runtime diagnostics missing');
      await page.screenshot({path:path.join(screenshots,'nox_v29_home_1440.png'),fullPage:false,timeout:60000});
      actual.push({width,route:'index.html',coreids:8,persona:5,worldButtons:14,render:d.worlds?.allMaterialAssetsReady?'PBR_READY':'PBR_CHECK_IN_SEPARATE_FULL_AUDIT'});
    }
    assert.deepEqual(exceptions,[],'Unhandled WEB script exception at '+width);
    await page.close();
  }
  console.log('NOX_V29_UNIFIED_REAL_CHROMIUM_PASS',JSON.stringify({checks:actual.length,viewports:2,realWindows:'NOT_TESTED',realNativeOneHost:'NOT_TESTED',results:actual}));
} finally {await browser.close()}
