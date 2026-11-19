/* NOX WEB29: one progress page, temporary chat dock, permanent menu route.
 * No model call, no job scheduler, no new memory, no mutation of the composer.
 * Same-origin frame is created on demand and removed on close (no hidden polling).
 */
(()=>{'use strict';
 if(window.NoxEvolutionDock)return;
 const script=document.currentScript;
 if(!script||!script.src)return;
 const base=new URL('.',script.src),pageURL=new URL('pc/progress.html',base),fullURL=new URL('progress.html',base);
 if(pageURL.origin!==location.origin)return;
 const css=document.createElement('link');css.rel='stylesheet';css.href=new URL('nox-evolution-dock.css',base).href;document.head.append(css);
 const icon='<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M3 17l5-6 4 3 8-10M16 4h4v4M3 21h18"/></svg>';
 let panel=null,frame=null,trigger=null,lastFocus=null;
 const anchor=(label,cls='')=>{const a=document.createElement('a');a.href=fullURL.href;a.className=cls;a.dataset.noxEvolution='';a.setAttribute('aria-label',label);a.innerHTML=icon;const t=document.createElement('span');t.textContent=label;a.append(t);return a;};
 function close(){if(!panel)return;panel.hidden=true;if(frame){frame.src='about:blank';frame.remove();frame=null;}trigger?.setAttribute('aria-expanded','false');lastFocus?.focus?.();}
 function open(){
  if(!panel||!trigger)return;
  if(!panel.hidden){close();return;}
  lastFocus=document.activeElement;const host=panel.parentElement,tools=host.querySelector('.nox-evolution-dock-tools');if(tools){const h=host.getBoundingClientRect(),t=tools.getBoundingClientRect();panel.style.bottom=Math.max(140,h.bottom-t.top+8)+'px';}panel.hidden=false;trigger.setAttribute('aria-expanded','true');
  frame=document.createElement('iframe');frame.className='nox-evolution-frame';frame.title='Развитие NOX — самоулучшение, знания и веса';
  frame.referrerPolicy='same-origin';frame.setAttribute('loading','eager');
  // Trusted same-origin original page: preserve owner's HttpOnly session. No tokens in URL.
  const u=new URL(pageURL);u.searchParams.set('embedded','1');frame.src=u.href;
  panel.querySelector('.nox-evolution-frame-host').append(frame);panel.querySelector('[data-nox-dock-close]').focus();
 }
 function installChat(){
  const composer=document.getElementById('chatForm');
  if(!composer)return false;
  if(document.getElementById('nox-evolution-dock'))return true;
  const region=document.querySelector('.v24-main,.chat-conversation,.nox-v22-center')||composer.parentElement;
  if(!region)return false;
  trigger=document.createElement('button');trigger.type='button';trigger.className='nox-evolution-trigger';trigger.innerHTML=icon;
  const label=document.createElement('span');label.textContent='Развитие NOX';trigger.append(label);
  trigger.setAttribute('aria-controls','nox-evolution-dock');trigger.setAttribute('aria-expanded','false');trigger.title='Три потока прогресса — открыть внутри чата';trigger.addEventListener('click',open);
  const toolbar=document.createElement('div');toolbar.className='nox-evolution-dock-tools';composer.insertAdjacentElement('beforebegin',toolbar);toolbar.append(trigger);
  panel=document.createElement('section');panel.id='nox-evolution-dock';panel.className='nox-evolution-dock';panel.hidden=true;panel.setAttribute('aria-label','Развитие NOX внутри чата');
  const bar=document.createElement('header');bar.className='nox-evolution-dock-bar';
  const heading=document.createElement('strong');heading.textContent='РАЗВИТИЕ NOX';bar.append(heading);
  const full=anchor('Отдельная страница','nox-evolution-full');full.target='_blank';full.rel='noopener';bar.append(full);
  const x=document.createElement('button');x.type='button';x.dataset.noxDockClose='';x.textContent='×';x.title='Вернуться к чату';x.setAttribute('aria-label','Закрыть панель развития');x.addEventListener('click',close);bar.append(x);
  const holder=document.createElement('div');holder.className='nox-evolution-frame-host';panel.append(bar,holder);region.append(panel);
  // Overlay only inside the original chat region; messages, draft and STOP remain mounted.
  region.classList.add('nox-evolution-host');
  panel.addEventListener('keydown',e=>{if(e.key==='Escape'){e.preventDefault();close();}});
  return true;
 }
 function installHome(){
  if(document.body.dataset.page!=='index')return;
  // Add a menu control, not a 15th planet or a replacement visual renderer.
  const insert=()=>{const nav=document.querySelector('.nox-center-rail .nox-rail-right,.nox-owner-nav,#nox-top-nav,.helion-deck');if(!nav||nav.querySelector('[data-nox-evolution-home]'))return;
   const a=anchor('Развитие NOX','nox-evolution-home');a.dataset.noxEvolutionHome='';a.title='Развитие NOX · самоулучшение · знания · веса';nav.append(a);};
  insert();const ob=new MutationObserver(insert);ob.observe(document.body,{childList:true,subtree:true});setTimeout(()=>ob.disconnect(),12000);
 }
 function init(){
  if(!installChat()){
   // Original chat may mount after DOMContentLoaded: keep one bounded observer.
   const pending=new MutationObserver(()=>{if(installChat())pending.disconnect();});
   pending.observe(document.body,{childList:true,subtree:true});
   setTimeout(()=>pending.disconnect(),12000);
   window.addEventListener('pagehide',()=>pending.disconnect(),{once:true});
  }
  installHome();
 }
 window.addEventListener('message',e=>{if(e.origin!==location.origin||!frame||e.source!==frame.contentWindow)return;if(e.data?.type==='nox-evolution:close')close();});
 window.addEventListener('pagehide',close);
 window.NoxEvolutionDock=Object.freeze({open,close,progressURL:fullURL.href,embedURL:pageURL.href,diagnostics:()=>({attached:!!panel,expanded:!!panel&&!panel.hidden,frameCount:frame?1:0,origin:pageURL.origin,modelCalls:0})});
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
})();
