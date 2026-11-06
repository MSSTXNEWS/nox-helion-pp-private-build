"""Add five accessible EXPRESS primary actions to an immutable R11 HOME copy.

The original HOME, host, menu and backend are never rewritten. Caller stages
only a disposable NSIS payload and verifies the published digest separately.
No synthetic install/model/training ACKs or permission changes are permitted.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

ORIGINAL_BYTES = 94908
ORIGINAL_SHA256 = "b57d58bb001c9826feb3bf7ff19510d047c7ec2926ee8b703538dfca886a960b"
MARKER = 'id="nox-express-primary"'

# Original controls are invoked only by a real user click. Unknown routes HOLD.
# MODELS delegates to the already installed original WPF bridge, which enforces
# native SID/ACL/consent and may legitimately return HOLD if offline.
INSERT = r'''<!-- NOX EXPRESS 5 original-home primary actions; no additional host -->
<style id="nox-express-primary-style">
#nox-express-primary{position:fixed;left:50%;bottom:12px;transform:translateX(-50%);z-index:990;display:flex;gap:7px;max-width:calc(100vw - 20px);width:max-content;flex-wrap:wrap;justify-content:center;padding:9px;border:1px solid rgba(115,207,255,.4);border-radius:18px;background:rgba(5,11,25,.94);box-shadow:0 0 28px rgba(60,140,225,.25);color:#eaf6ff;font:600 12px/1.3 system-ui,sans-serif}
#nox-express-primary button{--nox-planet:#4ba3f1;--nox-planet-light:#a7edff;appearance:none;cursor:pointer;min-height:70px;min-width:92px;display:flex;flex-direction:column;justify-content:center;align-items:center;gap:4px;padding:7px 11px;border:1px solid rgba(115,207,255,.45);border-radius:15px;background:linear-gradient(160deg,rgba(24,53,85,.94),rgba(6,15,33,.98));color:#f0faff;font:inherit;letter-spacing:.04em;text-shadow:0 1px 3px #020714}
#nox-express-primary button::before{content:"";display:block;width:30px;height:30px;flex:none;border-radius:50%;background:radial-gradient(circle at 29% 23%,#fff 0%,var(--nox-planet-light) 14%,var(--nox-planet) 43%,#08172d 86%);box-shadow:inset -4px -5px 8px rgba(1,5,17,.85),inset 2px 2px 5px rgba(255,255,255,.55),0 0 13px var(--nox-planet);animation:noxPrimaryFloat 5.6s ease-in-out infinite}
#nox-express-primary button[data-nox-primary = "CHAT"]{--nox-planet:#55b6f8;--nox-planet-light:#c3f2ff}
#nox-express-primary button[data-nox-primary = "INSTALL"]{--nox-planet:#e39863;--nox-planet-light:#ffe4b7}
#nox-express-primary button[data-nox-primary = "MODELS"]{--nox-planet:#a481ee;--nox-planet-light:#f4d8ff}
#nox-express-primary button[data-nox-primary = "LEARN"]{--nox-planet:#58c9ae;--nox-planet-light:#c7ffe5}
#nox-express-primary button[data-nox-primary = "SETTINGS"]{--nox-planet:#e3bc58;--nox-planet-light:#fff4bc}
#nox-express-primary button:nth-of-type(even)::before{animation-delay:-2.8s}
#nox-express-primary button:focus-visible::before{box-shadow:0 0 0 3px #e6fcff,0 0 17px var(--nox-planet)}
@keyframes noxPrimaryFloat{0%,100%{transform:translateY(0)}50%{transform:translateY(-3px)}}

#nox-express-primary button:hover,#nox-express-primary button:focus-visible{border-color:#9ce7ff;outline:2px solid #9ce7ff;outline-offset:2px}
#nox-express-primary [data-nox-state]{width:100%;font-size:11px;text-align:center;font-weight:400;min-height:14px}

/* At 800x600 WPF the native side panel can leave a 551–780px WebView2
   viewport. A1/status must not wrap one of the five ORIGINAL UIA actions. */
@media (min-width:551px) and (max-width:1120px){
html body #nox-express-primary{bottom:6px;left:calc(50% + 104px);width:min(650px,calc(100vw - 238px));max-width:calc(100vw - 238px);box-sizing:border-box;display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:5px;justify-content:stretch}
#nox-express-primary button[data-nox-primary]{width:100%;min-width:0;box-sizing:border-box;padding:7px 2px;white-space:nowrap;font-size:clamp(9px,1.5vw,12px);letter-spacing:0}
#nox-express-primary [data-nox-check="A1"],#nox-express-primary [data-nox-state]{grid-column:1/-1;min-width:0}
}
@media(max-width:550px){#nox-express-primary{bottom:max(3px,env(safe-area-inset-bottom,0px));width:calc(100vw - 12px);max-width:calc(100vw - 12px);display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:3px;padding:5px;box-sizing:border-box}#nox-express-primary button{width:100%;min-width:0;min-height:56px;padding:6px 1px;font-size:9px;letter-spacing:0;line-height:1.2;white-space:nowrap}#nox-express-primary button::before{width:22px;height:22px}#nox-express-primary [data-nox-state]{grid-column:1 / -1;min-width:0;overflow-wrap:anywhere}}
@media(prefers-reduced-motion:reduce){#nox-express-primary,#nox-express-primary *,#nox-express-primary button::before{animation:none!important;transition:none!important;scroll-behavior:auto!important}#nox-express-primary button::before{transform:none!important}}
#nox-express-primary [data-nox-check="A1"]{min-width:82px;min-height:27px;padding:4px 8px;font-size:10px;letter-spacing:.03em;line-height:1.2}
#nox-express-primary [data-nox-check="A1"]::before{display:none}
@media(max-width:550px){#nox-express-primary [data-nox-check="A1"]{grid-column:1/-1;min-height:30px;width:100%}}
</style>
<nav id="nox-express-primary" aria-label="NOX HELION EXPRESS — основные действия">
<button type="button" id="nox-express-primary-chat" data-nox-primary="CHAT" aria-label="CHAT">CHAT</button>
<button type="button" id="nox-express-primary-install" data-nox-primary="INSTALL" aria-label="INSTALL">INSTALL</button>
<button type="button" id="nox-express-primary-models" data-nox-primary="MODELS" aria-label="MODELS">MODELS</button>
<button type="button" id="nox-express-primary-learn" data-nox-primary="LEARN" aria-label="LEARN">LEARN</button>
<button type="button" id="nox-express-primary-settings" data-nox-primary="SETTINGS" aria-label="SETTINGS">SETTINGS</button>
<button type="button" data-nox-check="A1" aria-label="ПРОВЕРИТЬ A1">A1 · СТАТУС</button>
<span data-nox-state role="status" aria-live="polite"></span>
</nav>
<script id="nox-express-primary-bind">
(()=>{'use strict';
const nav=document.getElementById('nox-express-primary');if(!nav)return;
const state=nav.querySelector('[data-nox-state]');
// Render only an exact unique *existing* text-only original MENU label as a
// graphical symbol. Do not replace its element, listeners, route, or siblings.
// Unknown/multiple labels are left untouched for physical visual E07 HOLD.
function renderOriginalMenuGlyph(){
 const labels=Array.from(new Set(document.querySelectorAll('aside *, nav *, header *, .sidebar *')))
  .filter(el=>!nav.contains(el)&&el.children.length===0&&
     (el.textContent||'').trim()==='MENU');
 if(labels.length!==1)return false;
 const label=labels[0];
 const nodes=Array.from(label.childNodes).filter(n=>n.nodeType===3&&
     (n.textContent||'').trim()==='MENU');
 if(nodes.length!==1)return false;
 if(!label.hasAttribute('aria-label'))
   label.setAttribute('aria-label','Направления HELION');
 nodes[0].textContent='✦';
 label.dataset.noxOriginalMenuGlyph='true';
 return true;
}
// Original R11 may mount its unchanged sidebar after DOMContentLoaded.
// Keep the unique, text-only original owner and bound observation; never
// replace listeners/elements or treat a duplicate/unknown label as accepted.
function activateOriginalMenuGlyph(){
 if(renderOriginalMenuGlyph())return;
 const Observer=window.MutationObserver;
 if(typeof Observer!=='function'||!document.documentElement)return;
 let timer=null;
 const watcher=new Observer(()=>{
  if(!renderOriginalMenuGlyph())return;
  watcher.disconnect();
  if(timer!==null)window.clearTimeout?.(timer);
 });
 watcher.observe(document.documentElement,{childList:true,characterData:true,subtree:true});
 if(typeof window.setTimeout==='function')
  timer=window.setTimeout(()=>watcher.disconnect(),8000);
}
if(document.readyState==='loading')
 document.addEventListener('DOMContentLoaded',activateOriginalMenuGlyph,{once:true});
else activateOriginalMenuGlyph();

const screenNames={CHAT:['ЧАТ','CHAT'],INSTALL:['УСТАНОВКА','INSTALL'],LEARN:['ОБУЧЕНИЕ','LEARN'],SETTINGS:['НАСТРОЙКИ','SETTINGS']};
function safeOriginalLink(a){
 // No external/privileged routes from a text-matched original anchor.
 const href=(a.getAttribute('href')||'').trim();
 if(!href || href.startsWith('//') || /\\/.test(href) ||
    /^[A-Za-z][A-Za-z0-9+.-]*:/.test(href))return false;
 try{
   const destination=new URL(href,document.baseURI);
   const original=new URL(document.baseURI);
   if(destination.origin!==original.origin)return false;
   if(original.protocol==='file:')return destination.pathname===original.pathname && destination.search===original.search;
   return (original.protocol==='http:'||original.protocol==='https:') &&
          destination.protocol===original.protocol;
 }catch{return false;}
}
function findOriginalScreen(name){
 const terms=screenNames[name]||[];
 // Resolve only a pre-existing safe original route; otherwise explicit HOLD.
 const candidates=Array.from(document.querySelectorAll('a[href]')).filter(a=>!nav.contains(a)&&
   terms.includes((a.textContent||'').trim().toLocaleUpperCase('ru'))&&
   safeOriginalLink(a));
 // Never select the first of multiple source routes for a privileged action.
 return candidates.length===1?candidates[0]:null;
}
function findOriginalControl(name){
 // Bind to SOURCE-LOCKED R11 buttons, not invented anchor text or direct IPC.
 // Unknown, duplicated, replaced or disabled original controls must HOLD.
 const selectors={
   CHAT:'.nav button[data-screen="chat"]',
   INSTALL:'button#install-app',
   MODELS:'button#model-center',
   LEARN:'.nav button[data-screen="control"]',
   SETTINGS:'button.tile[data-menu-index="7"]'
 };
 const selector=selectors[name];if(!selector)return null;
 const matches=document.querySelectorAll(selector);
 if(matches.length!==1)return null;
 const button=matches[0];
 return button.tagName==='BUTTON'&&button.isConnected&&!button.disabled&&
        !nav.contains(button)?button:null;
}
// This is the immutable source-locked five-action HOME dock, not a name-based clone.
// Stable HTML ids aid WebView2 UIA; reordering, replacing or duplicating a node HOLDS.
const originalPrimaryButtons=Array.from(nav.querySelectorAll(':scope > button[data-nox-primary]'));
// ARIA boolean true is case-insensitive. A CSS-visible button in an
// accessibility-hidden/disabled original shell must never dispatch its owner.
function ariaSuppressed(el){
 let depth=0;
 for(;el;el=el.parentElement){
  if(++depth>64)return true;
  const hidden=el.getAttribute?.('aria-hidden');
  const disabled=el.getAttribute?.('aria-disabled');
  if((typeof hidden==='string'&&hidden.trim().toLowerCase()==='true')||
     (typeof disabled==='string'&&disabled.trim().toLowerCase()==='true'))return true;
 }
 return false;
}
function verifiedOriginalPrimaryDock(){
 const names=['CHAT','INSTALL','MODELS','LEARN','SETTINGS'];
 // UIA and keyboard admission must cover the ENTIRE original five-button dock:
 // one hidden/ARIA-suppressed sibling must not count as 5/5 real actions.
 if(!nav.isConnected||ariaSuppressed(nav)||nav.closest('[hidden],[inert],[aria-hidden="true"],[aria-disabled="true"]')||
    nav.getClientRects().length===0)return false;
 const dockStyle=window.getComputedStyle(nav);
 if(!dockStyle||dockStyle.display==='none'||dockStyle.visibility!=='visible'||
    dockStyle.pointerEvents==='none'||!Number.isFinite(Number(dockStyle.opacity))||
    Number(dockStyle.opacity)<=0)return false;
 const live=nav.querySelectorAll(':scope > button[data-nox-primary]');
 // UIA "visible" is not enough: a nonempty DOM rect can be clipped,
 // overlap its sibling or be covered by an overlay at the click target.
 // Fail closed; do not move or restyle the approved D02 controls.
 const viewportWidth=document.documentElement?.clientWidth;
 const viewportHeight=document.documentElement?.clientHeight;
 if(!Number.isFinite(viewportWidth)||!Number.isFinite(viewportHeight)||
    viewportWidth<=0||viewportHeight<=0)return false;
 const dockRects=[];
 // A CSS-transparent or pointer-blocked outer R11 shell can leave this
 // dock's own computed style and its child hit targets unchanged. Do not
 // accept invisible original HOME UIA controls as real user gestures.
 let ancestor=nav.parentElement,ancestryDepth=0;
 while(ancestor){
  if(++ancestryDepth>64 || ancestor.hidden===true || ancestor.inert===true ||
     ancestor.getAttribute?.('aria-hidden')==='true' ||
     ancestor.getAttribute?.('aria-disabled')==='true')return false;
  const inherited=window.getComputedStyle(ancestor);
  if(!inherited||inherited.display==='none'||inherited.visibility!=='visible'||
     inherited.pointerEvents==='none'||
     !Number.isFinite(Number(inherited.opacity))||
     Number(inherited.opacity)<=0)return false;
  ancestor=ancestor.parentElement;
 }
 return live.length===names.length&&names.every((name,i)=>{
  const button=live[i],id='nox-express-primary-'+name.toLowerCase();
  if(button!==originalPrimaryButtons[i]||button.tagName!=='BUTTON'||
     button.getAttribute('id')!==id||
     button.getAttribute('data-nox-primary')!==name||
     button.getAttribute('aria-label')!==name||
     button.getAttribute('type')!=='button'||
     (button.hasAttribute('role')&&button.getAttribute('role')!=='button')||
     document.querySelectorAll('[id="'+id+'"]').length!==1||
     !button.isConnected||button.disabled||button.hidden||ariaSuppressed(button)||button.matches?.(':disabled')===true||button.tabIndex!==0||
     button.closest('[hidden],[inert],[aria-hidden="true"],[aria-disabled="true"]')||
     button.getClientRects().length===0)return false;
  const rect=button.getBoundingClientRect();
  if(!rect||![rect.left,rect.top,rect.right,rect.bottom,rect.width,rect.height]
     .every(Number.isFinite)||rect.width<=0||rect.height<=0||
      // A centre hit alone cannot certify an unusably small real UIA target.
      // Approved five-column D02 remains >=44 CSS px at 320/390/800.
      rect.width<44||rect.height<44||
     rect.left<-.5||rect.top<-.5||
     rect.right>viewportWidth+.5||rect.bottom>viewportHeight+.5)return false;
  // Sub-pixel tolerance avoids a false HOLD from WebView2 fractional zoom.
  if(dockRects.some(other=>
      Math.min(rect.right,other.right)-Math.max(rect.left,other.left)>.5&&
      Math.min(rect.bottom,other.bottom)-Math.max(rect.top,other.top)>.5))
    return false;
  // DOM/UIA tab order must match the approved visual reading order. Accept
  // genuine adaptive wraps; never require a fixed one-row geometry.
  const previous=dockRects[dockRects.length-1];
  if(previous){
    if(Math.abs(rect.top-previous.top)<=1){
      if(rect.left<previous.right-.5)return false;
    }else if(rect.top<previous.bottom-.5)return false;
  }
  const hit=document.elementFromPoint(
      (rect.left+rect.right)/2,(rect.top+rect.bottom)/2);
  if(!hit||(hit!==button&&!button.contains(hit)))return false;
  dockRects.push(rect);
  const style=window.getComputedStyle(button);
  return !!style&&style.display!=='none'&&style.visibility==='visible'&&
     style.pointerEvents!=='none'&&Number.isFinite(Number(style.opacity))&&
     Number(style.opacity)>0;
 });
}
// Navigation-only original R11 buttons can be CSS-collapsed at 320/390px.
// A trusted EXPRESS click may reuse their original route, but MUST refuse
// disabled/inert/ARIA-suppressed navigation. Actual native owner actions below
// still require physical visibility, focus and an unobstructed hit target.
function originalNavigationAllowed(button){
 return !!button&&button.tagName==='BUTTON'&&button.isConnected&&
   !button.disabled&&!ariaSuppressed(button)&&button.matches?.(':disabled')!==true&&
   button.getAttribute('aria-disabled')!=='true'&&
   !button.closest('[hidden],[inert],[aria-hidden="true"],[aria-disabled="true"]');
}
function visibleOriginalOwnerTarget(button){
 // Never trigger privileged original R11 handlers through offscreen,
 // occluded or accessibility-disabled controls. Keep their design untouched.
 if(!button||button.tagName!=='BUTTON'||!button.isConnected||button.disabled||
    ariaSuppressed(button)||
    button.matches?.(':disabled')===true||
    button.getAttribute?.('aria-disabled')==='true'||
    button.closest('[hidden],[inert],[aria-hidden="true"],[aria-disabled="true"]')||
    button.getClientRects().length===0)return false;
 const width=document.documentElement?.clientWidth;
 const height=document.documentElement?.clientHeight;
 const rect=button.getBoundingClientRect();
 if(!Number.isFinite(width)||!Number.isFinite(height)||width<=0||height<=0||
    !rect||![rect.left,rect.top,rect.right,rect.bottom,rect.width,rect.height]
       .every(Number.isFinite)||rect.width<=0||rect.height<=0||
    rect.left<-.5||rect.top<-.5||rect.right>width+.5||rect.bottom>height+.5)
   return false;
 const style=window.getComputedStyle(button);
 if(!style||style.display==='none'||style.visibility!=='visible'||
    style.pointerEvents==='none'||!Number.isFinite(Number(style.opacity))||
    Number(style.opacity)<=0)return false;
 // Opacity and pointer-events are not inherited in computed styles.
 // A CSS-hidden parent still leaves the original child hit-testable, and
 // programmatic .click() would invoke its privileged owner handler.
 // Require every ancestor to be visibly interactive before INSTALL/LEARN.
 let ancestryDepth=0;
 for(let ancestor=button.parentElement;ancestor;ancestor=ancestor.parentElement){
   if(++ancestryDepth>64)return false;
   const inherited=window.getComputedStyle(ancestor);
   if(!inherited||inherited.display==='none'||
      inherited.visibility!=='visible'||inherited.pointerEvents==='none'||
      !Number.isFinite(Number(inherited.opacity))||
      Number(inherited.opacity)<=0)return false;
 }
 const hit=document.elementFromPoint((rect.left+rect.right)/2,(rect.top+rect.bottom)/2);
 return !!hit&&(hit===button||button.contains(hit));
}

// Availability is NOT an owner ACK: native WPF still decides consent/exit/files.
// Never synthesize a privileged INSTALL click when the real WebView2 bridge
// is absent or the host object's property access throws.
function originalInstallTransportPresent(){
 try{return typeof window.chrome?.webview?.postMessage==='function';}
 catch{return false;}
}
// A shortcut click can start the ORIGINAL native installer asynchronously.
// Without its actual owner exit/files receipt, never repeat this dock dispatch:
// duplicate native actions could race update/rollback on the same slot.
// The ORIGINAL in-panel INSTALL action and its consent/ACL remain unchanged.
let originalInstallDelegated=false;


nav.addEventListener('click',event=>{
 const target=event.target.closest('button[data-nox-primary]');
 if(!target||!nav.contains(target)||!event.isTrusted)return;
 // Prevent mutated submit/reset controls from causing a form default action
 // even when source-locked UIA admission returns HOLD. No original route change.
 event.preventDefault();
 // Refuse forged, reordered, duplicated or disabled dock controls before
 // delegating a native owner operation. Original five routes are unchanged.
 if(!verifiedOriginalPrimaryDock()){
   state.textContent='EXPRESS: состав кнопок изменён · HOLD';return;
 }
 if(!Array.prototype.includes.call(originalPrimaryButtons,target) ||
    target.getClientRects().length===0){
   state.textContent='EXPRESS: исходная кнопка недоступна · HOLD';return;
 }
 const name=target.getAttribute('data-nox-primary');
 if(name==='INSTALL'&&originalInstallDelegated){
   state.textContent='INSTALL: повторная передача без owner exit/file readback · HOLD';return;
 }
 state.textContent='';
 if(name==='INSTALL'&&!originalInstallTransportPresent()){
   state.textContent='INSTALL: исходный нативный WebView2 недоступен · HOLD';return;
 }
 if(name==='MODELS'&&!originalInstallTransportPresent()){
   state.textContent='MODELS: native WebView2 недоступен · HOLD';return;
 }
 // Main actions navigate to SOURCE-LOCKED real controls, never run
 // install, model downloads or training merely because their top-level
 // navigation button was clicked. The user still chooses the original action
 // inside its own panel, under existing native ACL and consent.
 const destinations={
   INSTALL:['control','button#pc-install','button#pc-install'],
   MODELS:['control','button#model-center','button#model-center'],
   // Top-level LEARN performs the original bounded training environment
   // diagnostic. Actual QLoRA start remains an explicit in-panel action with
   // dataset, immutable-revision and owner-confirmation gates.
   LEARN:['control','button#training-diagnostic','button#training-diagnostic']
 };
 if(Object.prototype.hasOwnProperty.call(destinations,name)){
   const [screen,selector,invokeSelector]=destinations[name];
   const navMatches=document.querySelectorAll('.nav button[data-screen="'+screen+'"]');
   const navControl=navMatches.length===1?navMatches[0]:null;
   const matches=document.querySelectorAll(selector);
   if(!originalNavigationAllowed(navControl)||matches.length!==1||
      !originalNavigationAllowed(matches[0])){
     state.textContent=name+': исходный элемент недоступен · HOLD';return;
   }
   // D03: original navigation may throw when its WebView2/screen owner tears down.
   // No privileged INSTALL retry, no consent/exit ACK on a failed transition.
   try{navControl.click();} // Reuse original showScreen/navigation, not a second UI.
   catch{state.textContent=name+': исходный переход завершился исключением · HOLD';return;}
   if(!document.getElementById(screen)?.classList.contains('active')){
     state.textContent=name+': исходный экран не открылся · HOLD';return;
   }
   const target=matches[0];
   if(target.getClientRects().length===0){
     state.textContent=name+': целевой элемент не виден · HOLD';return;
   }
   try{target.focus({preventScroll:false});}
   catch{state.textContent=name+': исходный фокус завершился исключением · HOLD';return;}
   if(document.activeElement!==target){
     state.textContent=name+': фокус оригинального элемента не подтверждён · HOLD';
     return;
   }
   // This trusted top-level user click delegates to an EXISTING original
   // R11 control. No direct privileged IPC, synthetic ACK or second backend.
   // INSTALL delegates to the original visible PC install control, which uses
   // the same native installApp owner without a synthetic second confirmation;
   // MODELS opens the original WPF Model Center; LEARN runs the original
   // environment diagnostic while QLoRA start remains separately consented.
   const invokeMatches=document.querySelectorAll(invokeSelector);
   if(invokeMatches.length!==1||invokeMatches[0]!==target||
      invokeMatches[0].tagName!=='BUTTON'||!invokeMatches[0].isConnected||
      invokeMatches[0].disabled||invokeMatches[0].getClientRects().length===0||
      (document.activeElement!==invokeMatches[0]||
       !visibleOriginalOwnerTarget(invokeMatches[0]))){
     state.textContent=name+': исходная функция недоступна · HOLD';return;
   }
   // Focus/navigation may tear down the native WebView2 bridge after
   // first admission. Both original WPF owners must recheck after focus.
   // No owner action or fabricated ACK when the transport disappears.
   if((name==='INSTALL'||name==='MODELS')&&!originalInstallTransportPresent()){
     state.textContent=name+': связь с нативным владельцем прервана · HOLD';return;
   }
   // D03 R5: do not overwrite a synchronous native owner rejection or
   // imply a physical exit/file result. One trusted click, no retry on throw.
   if(name==='INSTALL'){
     // The native command can have been issued even if its handler throws.
     // Fence before original click; never silently retry an unverified action.
     originalInstallDelegated=true;
     state.textContent='INSTALL: передача исходному владельцу · результат не подтверждён';
     try{invokeMatches[0].click();}
     catch{state.textContent='INSTALL: исходный обработчик завершился исключением · HOLD';}
     return;
   }
   // An existing MODELS/LEARN owner callback may fail during WebView2 teardown.
   // Keep exactly one original owner click and never issue an optimistic ACK.
   state.textContent=name+': передача исходному обработчику · результат не подтверждён';
   try{invokeMatches[0].click();}
   catch{state.textContent=name+': исходный обработчик завершился исключением · HOLD';}
   return;
 }
 // SETTINGS enters the original MENU first, then uses its ORIGINAL system tile.
 // No hidden-tile click can silently count as verified user navigation.
 if(name==='SETTINGS'){
   const menuEntries=document.querySelectorAll('.nav button[data-screen="menu"]');
   const systemTiles=document.querySelectorAll('button.tile[data-menu-index="7"]');
   if(menuEntries.length!==1||systemTiles.length!==1||
      !originalNavigationAllowed(menuEntries[0])||
      !originalNavigationAllowed(systemTiles[0])){
     state.textContent='SETTINGS: исходное направление недоступно · HOLD';return;
   }
   try{menuEntries[0].click();}
   catch{state.textContent='SETTINGS: исходное MENU завершилось исключением · HOLD';return;}
   const tile=systemTiles[0];
   if(!document.getElementById('menu')?.classList.contains('active')||
      tile.getClientRects().length===0){
     state.textContent='SETTINGS: исходное MENU не открылось · HOLD';return;
   }
   try{tile.focus({preventScroll:false});}
   catch{state.textContent='SETTINGS: фокус исходной СИСТЕМЫ завершился исключением · HOLD';return;}
   if(document.activeElement!==tile){
     state.textContent='SETTINGS: системная кнопка не получила фокус · HOLD';return;
   }
   if(!visibleOriginalOwnerTarget(tile)){
     state.textContent='SETTINGS: исходная системная кнопка перекрыта · HOLD';return;
   }
   try{tile.click();}
   catch{state.textContent='SETTINGS: исходная СИСТЕМА завершилась исключением · HOLD';return;}
   if(!document.getElementById('menu-detail')?.classList.contains('active')){
     state.textContent='SETTINGS: исходная СИСТЕМА не открылась · HOLD';return;
   }
   // Original Settings navigation must leave keyboard/assistive-technology
   // focus on the real visible BACK control, not on its newly hidden tile.
   // Only focus, never invoke a second action or native owner operation.
   const backButtons=Array.from(document.querySelectorAll('#menu-detail button'))
     .filter(button=>button.tagName==='BUTTON'&&button.isConnected&&
       !button.disabled&&
       ((button.getAttribute('aria-label')||button.textContent||'')
          .trim().replace(/\s+/g,' ').toLocaleUpperCase('ru')==='← НАЗАД В МЕНЮ'));
   if(backButtons.length!==1||backButtons[0].getClientRects().length===0){
     state.textContent='SETTINGS: исходная обратная кнопка не уникальна/скрыта · HOLD';return;
   }
   try{backButtons[0].focus({preventScroll:false});}
   catch{state.textContent='SETTINGS: фокус обратной кнопки завершился исключением · HOLD';return;}
   if(document.activeElement!==backButtons[0]||
      !visibleOriginalOwnerTarget(backButtons[0]))
     state.textContent='SETTINGS: исходная обратная кнопка без фокуса · HOLD';
   return;
 }
 // CHAT reuses its original source-bound screen, not a second router.
 // A clicked top-level action never fabricates a model reply or install ACK.
 const original=findOriginalControl(name)||findOriginalScreen(name);
 if(!original){state.textContent=name+': нет подтверждённого исходного экрана · HOLD';return;}
 if(original.tagName==='BUTTON'&&!originalNavigationAllowed(original)){
   state.textContent=name+': исходная навигация отключена · HOLD';return;
 }
 try{original.click();}
 catch{state.textContent=name+': исходный переход завершился исключением · HOLD';return;}
 if(name==='CHAT'&&!document.getElementById('chat')?.classList.contains('active'))
   state.textContent='CHAT: исходный экран не открылся · HOLD';
});

// Read-only original A1 native status. One physical click, one cryptographic
// request ID, no boot/tick, no fabricated owner consent, no second host.
const a1Button=nav.querySelector('button[data-nox-check="A1"]');
let a1Pending=false;
a1Button?.addEventListener('click',event=>{
 if(!event.isTrusted||a1Pending)return;
 // A torn WebView2 property accessor is a native HOLD, never an exception.
 let native,random;
 try{
  native=window.chrome?.webview;
  random=window.crypto?.getRandomValues;
 }catch{
  state.textContent='A1: доверенный OneHost недоступен · HOLD';return;
 }
 if(!native||typeof native.postMessage!=='function'||
    typeof native.addEventListener!=='function'||typeof random!=='function'){
   state.textContent='A1: доверенный OneHost недоступен · HOLD';return;
 }
 const bytes=new Uint8Array(16);
 try{window.crypto.getRandomValues(bytes);}
 catch{state.textContent='A1: защищённый идентификатор недоступен · HOLD';return;}
 const requestId=Array.from(bytes,x=>x.toString(16).padStart(2,'0')).join('');
 // A former transport callback must never finish a newer user request.
 let a1Settled=false;
 a1Pending=true;a1Button.disabled=true;
 state.textContent='A1: запрос нативного статуса…';
 let timer;
 const done=message=>{
   if(a1Settled)return;
   a1Settled=true;
   clearTimeout(timer);
   // Disconnect during callback cleanup is HOLD; restore UIA accessibility.
   let removed=true;
   try{native.removeEventListener('message',onNative);}
   catch{removed=false;}
   a1Pending=false;a1Button.disabled=false;
   state.textContent=removed?message:'A1: нативный транспорт потерян · HOLD';
 };
 // Authenticated transport completion may still carry owner/provider denial.
 function a1ReceiptDenied(envelope,depth=0,trail=new Set()){
  // A transport COMPLETED never overrules native SID/ACL/consent/provider denial.
  // Bound receipt traversal: cyclic, malformed or non-boolean ACKs HOLD.
  if(!envelope||typeof envelope!=='object'||Array.isArray(envelope)||
     depth>4||trail.has(envelope))return true;
  trail.add(envelope);
  const has=key=>Object.prototype.hasOwnProperty.call(envelope,key);
  // An explicit owner/consent refusal is never overridden by transport COMPLETED.
  // Missing optional fields are allowed; present fields require literal true.
  for(const key of ['ack','accepted','ok','success','approved','authorized','consented']){
   if(has(key)&&envelope[key]!==true)return true;
  }
  for(const key of ['error','error_code','errorCode','errorMessage','error_message']){
   if(!has(key))continue;
   const error=envelope[key];
   if(error!==null&&error!==undefined&&
      (typeof error!=='string'||error.trim()!==''))return true;
  }
  for(const key of ['status','state']){
   if(typeof envelope[key]==='string'&&
      /(?:HOLD|DENIED|REJECT|FAIL|ERROR|OFFLINE|CONSENT|UNAUTHORIZED|FORBIDDEN|PERMISSION_REQUIRED|AUTH_REQUIRED|AUTHORIZATION_REQUIRED|AUTHENTICATION_REQUIRED|NEEDS_AUTH|NOT_AUTHORIZED|NOT_AUTHENTICATED|SID_MISMATCH|ACL_MISMATCH|OWNER_MISMATCH|NOT_READY|PROVIDER_UNAVAILABLE|INVALID|STALE|TIMED_OUT|NOT_INSTALLED|RIGHTS_MISSING|ACTION_DISALLOWED|CANCELLED|ABORTED|REVOKED|EXPIRED)/i.test(envelope[key]))return true;
  }
  for(const key of ['result','receipt','ownerReceipt','owner_receipt','nativeResult','native_result','owner','ownerResult','owner_result']){
   if(!has(key)||envelope[key]===null||envelope[key]===undefined)continue;
   if(a1ReceiptDenied(envelope[key],depth+1,trail))return true;
  }
  trail.delete(envelope);
  return false;
 }
 const onNative=reply=>{
   if(a1Settled||reply?.isTrusted!==true||reply.source!==native)return;
   const value=reply.data;
   if(!value||value.kind!=='p02NativeResult'||value.requestId!==requestId||
      value.routeId!=='chat.commands')return;
   const owner=value.result;
   const verified=value.state==='COMPLETED'&&
       !a1ReceiptDenied(value)&&!a1ReceiptDenied(owner)&&
       owner?.schema==='NOX-A1-NATIVE-COMMAND-STATUS-v1'&&
       owner?.state==='ACTIVE_NATIVE_BOOT_RECEIPT'&&
       owner?.native_bound===true&&
       owner?.boot_state==='READY_FOR_EXISTING_IDLE_TICK';
   done(verified?'A1: живой нативный Boot подтверждён':'A1: нативный статус не подтверждён · HOLD');
 };
 try{native.addEventListener('message',onNative);}
 catch{
   a1Settled=true;
   a1Pending=false;a1Button.disabled=false;
   state.textContent='A1: подписка OneHost недоступна · HOLD';return;
 }
 timer=setTimeout(()=>{if(a1Pending)done('A1: нативный ответ не получен · HOLD');},12000);
 try{native.postMessage({kind:'p02.native',requestId,routeId:'chat.commands',
                       payload:{action:'selfbuilder.a1.status'}});}
 catch{done('A1: запрос отклонён OneHost · HOLD');}
});
})();
</script>
'''


def publish(original: bytes) -> tuple[bytes, dict]:
    """Return a derived HTML payload and strict non-release source receipt."""
    if type(original) is not bytes or len(original) != ORIGINAL_BYTES:
        raise ValueError("U08_ORIGINAL_HOME_BYTES_HOLD")
    original_sha = hashlib.sha256(original).hexdigest()
    if original_sha != ORIGINAL_SHA256:
        raise ValueError("U08_ORIGINAL_HOME_SHA_HOLD")
    try:
        html = original.decode("utf-8-sig")
    except UnicodeError as exc:
        raise ValueError("U08_ORIGINAL_HOME_UTF8_HOLD") from exc
    if html.lower().count("</body>") != 1 or MARKER in html or "nox-express-primary-bind" in html:
        raise ValueError("U08_ORIGINAL_HOME_HTML_ANCHOR_HOLD")
    # R11 original has a chatLog TDZ: a wheel listener is installed before
    # the later const declaration. Repair ONLY this integrity-pinned staged
    # copy so the remaining existing native HOME callbacks can initialize.
    # Original donors, host, permission gates and NSIS payload owners stay put.
    tdz_decl = "chatLog=document.getElementById('chat-log'),"
    tdz_anchor = "let chatScrollFrame=0;"
    if (html.count(tdz_decl) != 1 or html.count(tdz_anchor) != 1
            or html.index(tdz_anchor) >= html.index(tdz_decl)):
        raise ValueError("U07_ORIGINAL_CHATLOG_TDZ_PREIMAGE_HOLD")
    html = html.replace(tdz_decl, "", 1)
    html = html.replace(tdz_anchor,
                        "const chatLog=document.getElementById('chat-log');" + tdz_anchor, 1)

    close = html.lower().rfind("</body>")
    derived = (html[:close] + INSERT + html[close:]).encode("utf-8")
    if derived.count(b'data-nox-primary=') != 5:
        raise ValueError("U08_FIVE_PRIMARY_COUNT_HOLD")
    return derived, {
        "source_sha256": original_sha,
        "published_sha256": hashlib.sha256(derived).hexdigest(),
        "published_bytes": len(derived),
        "visible_primary_buttons": ["CHAT", "INSTALL", "MODELS", "LEARN", "SETTINGS"],
        "installed_ui_automation": "NOT_RUN",
        "release_accepted": False,
    }
