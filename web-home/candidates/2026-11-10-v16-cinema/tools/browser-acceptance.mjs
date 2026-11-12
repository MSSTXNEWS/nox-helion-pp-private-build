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
const report={source:url,sourceRevision:process.env.NOX_AUDIT_SOURCE_SHA||null,startedAt:new Date().toISOString(),browser:'Chromium SwiftShader (not a physical GPU)',cases:[],physicalGpuAcceptance:'HOLD'};
try{
 for(const [name,width,height] of viewports){
  const page=await browser.newPage({viewport:{width,height},deviceScaleFactor:1});
  const errors=[],backendUnavailable=[];
  page.on('pageerror',e=>errors.push('JS: '+e.message));
  page.on('response',r=>{if(r.status()>=400){const u=new URL(r.url());if(u.origin===new URL(url).origin&&u.pathname.startsWith('/api/'))backendUnavailable.push({status:r.status(),path:u.pathname});else errors.push('HTTP '+r.status()+' '+r.url())}});
  // Generic Chrome resource messages contain no URL. HTTP responses above capture the failing static assets.
  page.on('console',msg=>{if(msg.type()==='error'&&!msg.text().includes('Failed to load resource: the server responded'))errors.push('CONSOLE: '+msg.text())});
  let status=null,snapshot=null,assetCheck=null,ownerCheck=null,blocked=null;
  try{
   const response=await page.goto(url,{waitUntil:'domcontentloaded',timeout:45000});
   status=response?.status()||null;
   // Wait for the ORIGINAL WebGL renderer and HDRI/material maps, not a
   // fixed 5s screenshot race. A timed-out renderer remains HOLD.
   await page.waitForFunction(()=>{
     const diag=window.NOX_CINEMATIC_HEALTH?.snapshot?.();
     return diag?.core?.realRendered===true&&diag?.worlds?.allMaterialAssetsReady===true;
   },null,{timeout:25000,polling:250}).catch(()=>{});
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
     ownerCheck.portraitsHttp=await page.evaluate(async()=>{
       const expected={kv:'4f349edf31118301b2c5d42b0fe5ad2c17aea05fae5622afab90a5a00950584b',am:'67390d082d29d0a90f09e09866875318fdd4c562ea6791f0f51c958adcd28768',la:'e03b0611b237f23ecafbbc1dd6e0aec93aabf38a3bb772af28b1ed0e90e27eaa',ev:'981b21da200f6a4d1c1741a4f5849c9379eb52d781d661ecfdb093ca29652c87',kw:'005d246edce84b4cd0f3d005a5eddb03adbedf8fdfe310ce29e6b95c6a16361e'};
       return await Promise.all(Object.entries(expected).map(async([id,sha])=>{
         const r=await fetch('./assets/nox-owner-approved/nox-owner-persona-'+id+'.webp',{cache:'no-store'});
         if(!r.ok)return {id,status:r.status,verified:false};
         const bytes=await r.arrayBuffer(),hash=await crypto.subtle.digest('SHA-256',bytes);
         const digest=[...new Uint8Array(hash)].map(x=>x.toString(16).padStart(2,'0')).join('');
         return {id,status:r.status,bytes:bytes.byteLength,verified:digest===sha};
       }));
     });
   }
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
   // Actual owner V22: verify 8 linked CoreIDs, 14 original 3D selectors,
   // reversible mode switch and honest approved portrait interaction.
   ownerCheck.v22=await page.evaluate(()=>{
    const q=s=>document.querySelector(s);
    const rect=e=>{const r=e?.getBoundingClientRect();return r?{top:r.top,bottom:r.bottom,left:r.left,right:r.right}:null};
    const p=rect(q('.nox-owner-personas')),a=rect(q('.nox-owner-actions')),cta=rect(q('#noxCoreEntry'));
    return {ready:!!window.NOX_OWNER_RELEASE_V22,
      ics:window.NOX_OWNER_RELEASE_V22?.coreCount,
      originalWorldControls:q('section.nox-orbital-controls')?.querySelectorAll('button').length||0,
      coreNames:[...document.querySelectorAll('.nox-owner-core span')].map(e=>e.textContent.trim()),
      personaName:q('.nox-owner-persona[data-idx="4"]')?.getAttribute('aria-label'),
      resonanceBeforePersonas:!!(cta&&p&&cta.bottom<=p.top+4),
      personasBeforeActions:!!(p&&a&&p.bottom<=a.top+4)};
   });
   if(!ownerCheck.v22.ready||ownerCheck.v22.ics!==8||ownerCheck.v22.originalWorldControls!==14)
    throw Error('NOX_V22_CORE_WORLD_CONTRACT_MISSING:'+JSON.stringify(ownerCheck.v22));
   if(ownerCheck.v22.coreNames.some(n=>!/[^\x00-\x7f]/.test(n))||!ownerCheck.v22.personaName?.includes('КАССИЕН ВЕЙР'))
    throw Error('NOX_V22_CANONICAL_LABEL_MISSING');
   if(width<=600&&(!ownerCheck.v22.resonanceBeforePersonas||!ownerCheck.v22.personasBeforeActions))
    throw Error('NOX_V22_MOBILE_OWNER_BANDS_COLLIDE');
   // V24 fidelity: runtime computed styles, not only asset existence.
   ownerCheck.v24=await page.evaluate(()=>{
     const st=(selector,pseudo='')=>{const e=document.querySelector(selector);return e?getComputedStyle(e,pseudo):null};
     const d02=st('#noxEclipseCanvas'),worlds=st('#noxWorldsV6Canvas');
     const shell=st('.nox-owner-core','::before');
     const arch=st('.nox-owner-architecture'),floor=st('.nox-owner-floor');
     const fallback=st('.nox-owner-core-still');
     return {
       ready:!!window.NOX_VISUAL_SOURCE_LOCK_V24,
       d02Filter:d02?.filter,worldFilter:worlds?.filter,
       d02Transform:d02?.transform,
       coreShellAnimation:shell?.animationName,
       motionOwner:document.body.dataset.noxMotionOwner,
       spatialAnimation:st('.nox-owner-core')?.animationName,
       coreShellHasOriginalMaterial:!!shell?.backgroundImage?.includes('repeating-conic-gradient'),
       architectureClip:arch?.clipPath,floorClip:floor?.clipPath,
       floorDuplicateTextMask:floor?.maskImage||floor?.webkitMaskImage||'none',
       originalFallbackHidden:document.body.dataset.noxD02Rendered==='true'?
          fallback?.display==='none':null,
       originalWebglRendered:window.NOX_CINEMATIC_HEALTH?.snapshot?.()?.core?.realRendered===true,
       pbrHdrReady:window.NOX_CINEMATIC_HEALTH?.snapshot?.()?.worlds?.allMaterialAssetsReady===true,
       gsapEngine:window.NOX_OWNER_FIDELITY_V21?.motionEngine||null,
       liquidGlassInstances:window.NOX_GLASS_INTEGRATION?.attached?.()??null
     };
   });
   if(!ownerCheck.v24.ready||ownerCheck.v24.d02Filter!=='none'||
      ownerCheck.v24.worldFilter!=='none'||ownerCheck.v24.d02Transform!=='none'||
      !ownerCheck.v24.coreShellHasOriginalMaterial||
      !ownerCheck.v24.architectureClip?.includes('36%')&&width>600||
      !ownerCheck.v24.floorClip?.includes('92%'))
      throw Error('NOX_V24_ORIGINAL_VISUAL_FIDELITY_HOLD:'+JSON.stringify(ownerCheck.v24));
   // Original owner image stays SHA-locked. Verify the approved art is NOT
   // painted with duplicate baked-in navigation labels behind live buttons.
   if(ownerCheck.v24.floorDuplicateTextMask==='none'||
      !ownerCheck.v24.floorDuplicateTextMask.includes('linear-gradient')||
      (width<=600&&!ownerCheck.v24.architectureClip?.includes('9%'))||
      (width>600&&!ownerCheck.v24.architectureClip?.includes('8%')))
      throw Error('NOX_V24_DUPLICATE_BACKGROUND_TEXT_NOT_MASKED:'+JSON.stringify(ownerCheck.v24));
   if(name==='1440'&&(!ownerCheck.v24.originalWebglRendered||!ownerCheck.v24.pbrHdrReady||
       ownerCheck.v24.gsapEngine!=='gsap-vendor'||!(ownerCheck.v24.liquidGlassInstances>0)))
      throw Error('NOX_V24_ORIGINAL_WOW_ENGINE_RUNTIME_MISSING:'+JSON.stringify(ownerCheck.v24));
   if(ownerCheck.v24.motionOwner==='GSAP'&&ownerCheck.v24.spatialAnimation!=='none')
      throw Error('NOX_V24_DOUBLE_ORBIT_ENGINE_RUNNING');
   if(ownerCheck.v24.originalWebglRendered&&ownerCheck.v24.originalFallbackHidden!==true)
      throw Error('NOX_V24_APPROVED_STILL_DOUBLE_EXPOSED');
   if(name==='1440'||name==='320'){
    const toggle=page.locator('.nox-owner-mode');
    await toggle.click();
    await page.waitForFunction(()=>document.body.dataset.noxOwnerLayout==='PBR'&&document.body.dataset.noxOwnerControls==='true',{timeout:10000});
    const worldCheck=await page.evaluate(()=>({alpha:Number(getComputedStyle(document.getElementById('noxWorldsV6Canvas')).opacity),
      controls:[...document.querySelectorAll('section.nox-orbital-controls button')].length}));
    if(worldCheck.controls!==14||worldCheck.alpha<.8)throw Error('NOX_V22_14_WORLDS_SWITCH_NOT_VISIBLE:'+JSON.stringify(worldCheck));
    const worldStyle=await page.evaluate(()=>getComputedStyle(document.getElementById('noxWorldsV6Canvas')).filter);
    if(worldStyle!=='none')throw Error('NOX_V24_PBR_MATERIAL_COLORS_DISTORTED:'+worldStyle);
    ownerCheck.v22.pbrWorldCheck=worldCheck;
    if(name==='1440'){
      // Explicit hit-target test for all 14 selectors: no other planet may
      // capture the center of a selected button. The WebGL remains unmodified.
      const originalHitTargets=await page.evaluate(()=>{
       const nodes=[...document.querySelectorAll('section.nox-orbital-controls button')];
       const items=nodes.map((node,index)=>{
         const r=node.getBoundingClientRect(),cx=r.left+r.width/2,cy=r.top+r.height/2;
         const hit=document.elementFromPoint(cx,cy);
         return {index,width:r.width,height:r.height,
           unobstructed:hit===node||node.contains(hit),
           hit:hit?.closest('button')?.getAttribute('title')||null};
       });
       return items;
      });
      if(originalHitTargets.length!==14||originalHitTargets.some(item=>!item.unobstructed))
       throw Error('NOX_ORIGINAL_14_BUTTON_OVERLAP:'+JSON.stringify(originalHitTargets));
      ownerCheck.v24.originalSelectorHitTargets=originalHitTargets.length;

      // Independent original-renderer evidence: this is the actual Three
      // scene's diagnostic output, not merely 14 HTML nodes or a mock status.
      const materials=await page.evaluate(()=>window.NOX_PHYSICAL_WORLDS_QA?.());
      const mat=materials?.materialAudit||[];
      if(materials?.count!==14||mat.length!==14||
         !materials.allMaterialAssetsReady||materials.hdrEnvironment!=='READY'||
         materials.planetMapsReady!==8||materials.metalMapsReady!==4||
         materials.metalMapsFailed?.length||
         mat.filter(v=>v.category==='asteroid').length!==3||
         mat.filter(v=>v.category!=='asteroid').length!==11||
         mat.some(v=>!Number.isFinite(v.roughness)||!Number.isFinite(v.metalness)||
                     v.roughness<0||v.roughness>1||v.metalness<0||v.metalness>1)||
         mat.some(v=>v.category!=='asteroid'&&!v.textureLoaded))
        throw Error('NOX_ORIGINAL_14_REAL_MATERIALS_NOT_READY:'+JSON.stringify({
         count:materials?.count,hdri:materials?.hdrEnvironment,maps:materials?.planetMapsReady,
         metal:materials?.metalMapsReady,failed:materials?.metalMapsFailed,
         loaded:mat.map(v=>[v.index,v.name,v.type,v.textureLoaded])
        }));
      const lighting=materials?.sceneLighting||{};
      if(!lighting.applied||!Number.isFinite(lighting.keyIntensity)||
         lighting.keyIntensity<=0||!Number.isFinite(lighting.exposure)||lighting.exposure<=0)
        throw Error('NOX_ORIGINAL_CINEMATIC_LIGHT_NOT_APPLIED:'+JSON.stringify(lighting));
      ownerCheck.v24.originalMaterialAudit={count:14,hdri:'READY',planetTextures:8,
       metalTextures:4,asteroids:3,physicalMaterials:11,lightScene:lighting.scene,
       lightChanges:lighting.changes,lightIntensity:lighting.keyIntensity,
       exposure:lighting.exposure,source:'NOX_PHYSICAL_WORLDS_QA',hardwareGpu:'NOT_TESTED'};
      // Verify the original world geometry is still rotating independently.
      const rotationsBefore=mat.map(x=>x.axialRotationRadians);
      await page.waitForTimeout(1100);
      const rotationsAfter=await page.evaluate(()=>window.NOX_PHYSICAL_WORLDS_QA?.().materialAudit
        .map(x=>x.axialRotationRadians));
      const moving=rotationsAfter?.filter((x,i)=>Math.abs(x-rotationsBefore[i])>0.0003).length||0;
      if(moving<8)throw Error('NOX_ORIGINAL_AXIAL_ROTATION_NOT_RUNNING:'+moving);
      ownerCheck.v24.rotatingMeshes=moving;
      await page.screenshot({path:path.join(out,'1440-pbr-14-original-materials.png'),fullPage:false,timeout:30000});

      // Exercise all 14 ORIGINAL controls, not just count them.
      const controls=page.locator('section.nox-orbital-controls button');
      for(let i=0;i<14;i++){
        const button=controls.nth(i);
        if(!await button.isEnabled())throw Error('NOX_V22_ORIGINAL_SELECTOR_DISABLED:'+i);
        await button.click({timeout:6000});
        await page.waitForFunction(index=>{
          const b=document.querySelectorAll('section.nox-orbital-controls button')[index];
          return b?.getAttribute('aria-pressed')==='true';
        },i,{timeout:3000});
      }
      ownerCheck.v22.originalWorldClicksPassed=14;
      // Restore the source's neutral theme, skin and balanced GPU profile
      // before capturing the art-direction screenshot.
      await page.locator('section.nox-orbital-controls button[data-home-preset="black-sun"]').click();
      await page.locator('section.nox-orbital-controls button.nox-world-profile').first().click();
      await page.locator('#homeModes > button[data-mode="BALANCED"]').click();
    }
    if(name==='320'){
      const exit=page.locator('.nox-v22-exit-worlds');
      if(!await exit.isVisible())throw Error('NOX_V22_MOBILE_PBR_EXIT_NOT_VISIBLE');
      await exit.click();
    }else await toggle.click();
    await page.waitForFunction(()=>document.body.dataset.noxOwnerLayout==='CINEMA',{timeout:10000});
    ownerCheck.v22.restoredEightCores=true;
    if(name==='1440'){
      const actions=page.locator('.nox-owner-actions button');
      await actions.nth(1).click();
      if(await page.evaluate(()=>document.body.dataset.noxOwnerHud)!=='true')
        throw Error('NOX_V22_MONITOR_BUTTON_NOT_WORKING');
      await actions.nth(1).click();
      await actions.nth(2).click();
      if(await page.evaluate(()=>document.body.dataset.noxOwnerControls)!=='true')
        throw Error('NOX_V22_GRAPHICS_BUTTON_NOT_WORKING');
      await actions.nth(2).click();
      ownerCheck.v22.monitorAndGraphicsButtonsPassed=true;
    }
   }
   if(name==='1440'){
    await page.locator('.nox-owner-persona[data-idx="4"]').click();
    const modal=page.locator('dialog.nox-v22-persona-dialog[open]');
    await modal.waitFor({timeout:8000});
    if(!(await modal.locator('img').getAttribute('src')).endsWith('nox-owner-persona-kw.webp'))
     throw Error('NOX_V22_OWNER_KW_IMAGE_MISMATCH');
    await modal.locator('button').click();
    ownerCheck.v22.personaModalPassed=await modal.count()===0;
   }
   if(name==='4k'){
     await page.screenshot({path:path.join(out,name+'.jpg'),type:'jpeg',quality:70,fullPage:false,timeout:90000});
   }else await page.screenshot({path:path.join(out,name+'.png'),fullPage:true,timeout:30000});
  }catch(e){errors.push('RUN: '+String(e.message||e))}
  const rendered=!!(snapshot?.core?.realRendered&&snapshot?.worlds?.allMaterialAssetsReady&&snapshot?.effects?.errors?.length===0);
  const acceptance=blocked?'BLOCKED_SSO':!snapshot?'HOLD_NO_RUNTIME_DIAGNOSTICS':rendered&&errors.length===0?'BROWSER_CANDIDATE':'HOLD';
  report.cases.push({viewport:name,width,height,httpStatus:status,acceptance,blocked,diagnostics:snapshot,assetCheck,ownerCheck,backendUnavailable,errors});
  await fs.writeFile(path.join(out,'progress-report.json'),JSON.stringify({
    ...report,stage:'VIEWPORT_'+name,completedViewportCount:report.cases.length
  },null,2));
  console.log('NOX_E2E_VIEWPORT',name,acceptance,errors.slice(0,2));
  await page.close();
 }
 // Cross-section smoke checks: no fake backends, no hidden failures.
 const pages=['index.html','chat.html','cinema.html','install.html','memory.html','models.html','projects.html','settings.html','system.html','training.html'];
 report.sections=[];
 for(const name of pages){
  const page=await browser.newPage({viewport:{width:1440,height:900}});
  const errors=[],backendUnavailable=[];page.on('pageerror',e=>errors.push(e.message));page.on('response',r=>{if(r.status()>=400){const u=new URL(r.url());if(u.origin===new URL(url).origin&&u.pathname.startsWith('/api/'))backendUnavailable.push({status:r.status(),path:u.pathname});else errors.push('HTTP '+r.status()+' '+r.url())}});
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
    const deadNavigation=[...document.querySelectorAll('a[href]')].filter(a=>['#','javascript:void(0)','javascript:;'].includes((a.getAttribute('href')||'').trim().toLowerCase())).length;
    const disabledButtons=buttons.filter(b=>b.disabled).map(b=>({name:(b.textContent||b.getAttribute('aria-label')||'').trim().slice(0,75),id:b.id||''})).slice(0,30);
    const buttonInventory=buttons.filter(b=>{const cs=getComputedStyle(b);const r=b.getBoundingClientRect();return cs.display!=='none'&&cs.visibility!=='hidden'&&r.width>1&&r.height>1}).map(b=>({name:(b.textContent||b.getAttribute('aria-label')||'').trim().slice(0,64),id:b.id||'',disabled:b.disabled||b.getAttribute('aria-disabled')==='true',type:b.type})).slice(0,130);
    return {v19Style:!!document.querySelector('link[href*="nox-universe-v19.css"]'),v19Script:!!window.NOX_UNIVERSE_V19,sharedStyle:!!document.querySelector('link[href*="nox-global-wow-v18.css"]'),sharedScript:!!window.NOX_WOW_GLOBAL_V18,visibleSelects:visibleSelects.length,choiceGroups:document.querySelectorAll('.nox-wow-choice-group').length,buttons:buttons.length,missingLinks,deadNavigation,disabledButtons,buttonInventory};
   });
   if(name==='chat.html'){
    await page.waitForFunction(()=>!!window.NOX_CHAT_TRAINING_V23,{timeout:10000});
    checks.trainingEvidencePanel=!!await page.locator('#nox-chat-training-v23').count();
    checks.trainingEvidenceHold=(await page.locator('#nox-chat-training-v23 .nox-chat-training-state').textContent()).includes('HOLD');
    checks.trainingEvidenceNoFakePercent=!(await page.locator('#nox-chat-training-v23 .nox-chat-training-data').textContent()).includes('%');
    checks.trainingRealRoute=(await page.locator('#nox-chat-training-v23 a').getAttribute('href'))==='./training.html';
    checks.trainingProofRefreshDisabled=await page.locator('#nox-chat-training-v23 button').isDisabled();
    if(!checks.trainingEvidencePanel||!checks.trainingEvidenceHold||!checks.trainingEvidenceNoFakePercent||
      !checks.trainingRealRoute||!checks.trainingProofRefreshDisabled)
      errors.push('NOX_V23_CHAT_TRAINING_STATIC_PREVIEW_MUST_SHOW_HOLD_AND_GENUINE_TRAINING_ROUTE');
   }
   if(name==='system.html'||name==='training.html'){
    await page.waitForFunction(()=>!!window.NOX_PROGRESS_PANEL,{timeout:7000});
    await page.locator('#nox-evidence-progress button').first().click();
    await page.waitForFunction(()=>document.querySelector('.nox-evidence-status')?.textContent?.includes('HOLD'),{timeout:7000});
    checks.progressPanel=!!await page.locator('#nox-evidence-progress').count();
    checks.progressProofHold=(await page.locator('.nox-evidence-status').textContent()).includes('HOLD');
    checks.progressSyntheticPercentVisible=await page.locator('.nox-evidence-metric').count()>0;
    if(!checks.progressPanel||!checks.progressProofHold||checks.progressSyntheticPercentVisible)
      errors.push('NOX_PROGRESS_MUST_HOLD_WITHOUT_CHECKPOINT_AND_TRAINER_HASHES');
   }
  }catch(e){errors.push(String(e))}
  console.log('NOX_E2E_ROUTE',name,errors.length?'HOLD':'CHECKED',errors.slice(0,2));
  report.sections.push({name,status,checks,backendUnavailable,errors,acceptance:status===200&&checks?.sharedStyle&&checks?.sharedScript&&checks?.v19Style&&checks?.v19Script&&checks.visibleSelects===0&&checks.deadNavigation===0&&errors.length===0?'PAGE_UI_PASS':'HOLD'});
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
  // Owner-approved HOME has its own visible menu button; legacy launcher is intentionally hidden.
  const ownerMenu=p.locator('.nox-owner-actions button').first();
  if(await ownerMenu.isVisible())await ownerMenu.click();else await p.locator('.nox-v19-launch').click();
  await p.waitForSelector('.nox-v19-panel:not([hidden])',{timeout:10000});
  const moduleButtons=await p.locator('.nox-v19-tabs button').allTextContents();
  for(const name of ['Кинотеатр','Книги','Календарь','Галерея','Эффекты','Новости','Уведомления','Погода','Валюта','Браузер','Разделы'])
   if(!moduleButtons.includes(name))throw Error('NOX_V19_MISSING_MODULE_BUTTON_'+name);
  await p.getByRole('button',{name:'Кинотеатр',exact:true}).click();
  await p.waitForSelector('video.nox-v19-video',{timeout:12000});
  for(const actionName of ['СОХРАНИТЬ ПОЗИЦИЮ','НА ВЕСЬ ЭКРАН','−10 С','+10 С']){
   if(!await p.getByRole('button',{name:actionName,exact:true}).isDisabled())
    throw Error('NOX_INERT_MEDIA_BUTTON_NOT_DISABLED:'+actionName);
  }
  await p.getByRole('button',{name:'Календарь',exact:true}).click();
  try{await p.waitForSelector('.nox-v19-calendar.fc .fc-toolbar',{timeout:13000});}
  catch(e){
    const diag=await p.evaluate(()=>({calendarMarkup:document.querySelector('.nox-v19-calendar')?.innerHTML?.slice(0,400),
      status:document.querySelector('.nox-v19-status')?.textContent,
      currentModule:document.querySelector('.nox-v19-tabs button[aria-pressed="true"]')?.textContent,
      fullCalendarLoaded:!!window.FullCalendar,
      fullCalendarType:typeof window.FullCalendar?.Calendar}));
    await p.screenshot({path:path.join(out,'calendar-diagnostic.png'),fullPage:true});
    throw Error('NOX_CALENDAR_RUNTIME_HOLD '+JSON.stringify(diag)+' '+String(e.message).slice(0,230));
  }
  await p.getByPlaceholder('Название события').fill('NOX-CI-TEST');
  await p.locator('.nox-v19-card input[type="date"]').first().fill('2026-11-11');
  await p.getByRole('button',{name:'ДОБАВИТЬ СОБЫТИЕ'}).click();
  const events=await p.evaluate(()=>JSON.parse(localStorage.getItem('nox-v19-calendar-events')||'[]'));
  const created=events.some(e=>e.title==='NOX-CI-TEST');
  await p.locator('.fc-event').filter({hasText:'NOX-CI-TEST'}).first().click({timeout:12000});
  const deleteButton=p.getByRole('button',{name:'УДАЛИТЬ ВЫБРАННОЕ'});
  if(!await deleteButton.isEnabled())throw Error('NOX_CALENDAR_SELECTED_DELETE_NOT_ENABLED');
  p.once('dialog',dialog=>dialog.accept());
  await deleteButton.click();
  const retained=await p.evaluate(()=>JSON.parse(localStorage.getItem('nox-v19-calendar-events')||'[]'));
  report.v19Modules.push({name:'Календарь',source:'FullCalendar local: create, select, delete',passed:created&&!retained.some(e=>e.title==='NOX-CI-TEST')});
  await p.getByRole('button',{name:'Галерея',exact:true}).click();
  const tinyPng=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jzF8AAAAASUVORK5CYII=','base64');
  await p.locator('.nox-v19-card input[type=file]').first().setInputFiles({name:'test.png',mimeType:'image/png',buffer:tinyPng});
  await p.waitForSelector('.nox-v19-gallery a',{timeout:15000});
  await p.waitForFunction(()=>!!document.querySelector('link[href*="photoswipe.css"]'),{timeout:12000});
  await p.locator('.nox-v19-gallery a').first().click();
  await p.waitForSelector('.pswp.pswp--open[role="dialog"]',{timeout:15000});
  const lightboxOpened=await p.locator('.pswp.pswp--open[role="dialog"]').count()===1;
  // Close the actual PhotoSwipe overlay before testing underlying buttons.
  // Escape alone is asynchronous: without waiting, an overlay can intercept the next click.
  const closeButton=p.locator('.pswp.pswp--open .pswp__button--close');
  if(await closeButton.count())await closeButton.click();
  else await p.keyboard.press('Escape');
  await p.waitForFunction(()=>!document.querySelector('.pswp.pswp--open'),{timeout:12000});
  report.v19Modules.push({name:'Галерея',source:'PhotoSwipe local',passed:lightboxOpened});
  await p.getByRole('button',{name:'Эффекты',exact:true}).click();
  await p.getByRole('button',{name:'ECO · 15'}).click();
  await p.waitForFunction(()=>!!document.querySelector('#nox-v19-particles canvas') &&
      /GPU-эффекты: ECO/.test(document.querySelector('.nox-v19-status')?.textContent||''),{timeout:25000});
  const realCanvas=await p.evaluate(()=>{const c=document.querySelector('#nox-v19-particles canvas');return !!c&&c.width>0&&c.height>0});
  await p.getByRole('button',{name:'STOP FX'}).click();
  const stopped=await p.evaluate(()=>!document.querySelector('#nox-v19-particles canvas')&&/FX STOP/.test(document.querySelector('.nox-v19-status')?.textContent||''));
  report.v19Modules.push({name:'Эффекты',source:'tsParticles local',passed:realCanvas&&stopped,physicalGpu:'NOT_TESTED'});
  // Local TXT reader: no user document leaves the browser.
  await p.getByRole('button',{name:'Книги',exact:true}).click();
  for(const nav of ['◀ НАЗАД','ВПЕРЁД ▶'])
   if(!await p.getByRole('button',{name:nav,exact:true}).isDisabled())
    throw Error('NOX_INERT_READER_NAV_NOT_DISABLED:'+nav);

  await p.locator('.nox-v19-card input[type="file"]').first().setInputFiles({
    name:'nox-ci-reader.txt',mimeType:'text/plain',
    buffer:Buffer.from('NOX VERIFIED LOCAL READER SMOKE', 'utf8')});
  await p.waitForSelector('.nox-v19-text',{timeout:12000});
  report.v19Modules.push({name:'Книги (TXT)',source:'existing NOX reader',passed:
    (await p.locator('.nox-v19-text').textContent()).includes('NOX VERIFIED LOCAL READER SMOKE')});
  // Fuzzy search must use actual 130 approved sections and the local Fuse.js bundle.
  await p.getByRole('button',{name:'Разделы',exact:true}).click();
  await p.waitForFunction(()=>!!window.Fuse&&document.querySelectorAll('.nox-v19-sections button').length>0,{timeout:14000});
  await p.getByPlaceholder('Поиск раздела').fill('Кинотеатр');
  await p.waitForFunction(()=>[...document.querySelectorAll('.nox-v19-sections button')].some(b=>b.textContent.includes('Кинотеатр')),{timeout:14000});
  const bogus=await p.locator('.nox-v19-sections button.nox-v19-planned,.nox-v19-sections button[disabled]').count();
  if(bogus)throw Error('NOX_FAKE_CATALOG_BUTTONS_PRESENT:'+bogus);
  report.v19Modules.push({name:'Поиск разделов',source:'Fuse.js local + canonical catalog',passed:true});
 }catch(e){moduleErrors.push(String(e?.message||e))}
 report.v19ModuleErrors=moduleErrors;
 await p.close();
}finally{await browser.close()}
report.completedAt=new Date().toISOString();
report.summary={browserCandidates:report.cases.filter(c=>c.acceptance==='BROWSER_CANDIDATE').length,total:report.cases.length,physicalGpu:'NOT_TESTED',v19ModulesPassed:report.v19Modules?.filter(x=>x.passed).length||0,pageUiPassed:report.sections?.filter(x=>x.acceptance==='PAGE_UI_PASS').length??0};
await fs.writeFile(path.join(out,'report.json'),JSON.stringify(report,null,2));
console.log(JSON.stringify(report.summary));
if(report.cases.some(c=>!c.ownerCheck?.ready||c.ownerCheck.cores?.length!==8||c.ownerCheck.personas?.length!==5||!c.ownerCheck.originalWebgl)||report.cases.some(c=>c.ownerCheck?.artHttp&&!c.ownerCheck.artHttp.verified)||report.cases.some(c=>c.ownerCheck?.portraitsHttp&&c.ownerCheck.portraitsHttp.some(p=>!p.verified))||report.summary.v19ModulesPassed!==5 || report.v19ModuleErrors?.length || report.summary.pageUiPassed!==10 || report.summary.browserCandidates!==viewports.length || report.cases.some(c=>c.assetCheck && c.assetCheck.passed!==14))process.exitCode=1;
