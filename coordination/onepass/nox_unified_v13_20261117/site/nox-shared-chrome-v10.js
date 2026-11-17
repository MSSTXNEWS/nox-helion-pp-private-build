/* NOX V10: the same visual mini-header on every page, using HOME routes. No dropdowns and no second navigation design. */
(()=>{'use strict';
if(window.NOX_SHARED_UI_V10)return;
const D=document,H=D.documentElement,B=D.body;
const rootURL=new URL(".",document.currentScript.src).href;
const ROUTES=[["index.html","Ядро","home"],["system.html","Система","system"],["training.html","Обучение","training"],["dispatcher.html","Очередь задач","dispatcher"],["system.html#dashboard-load-history","Отчёты","reports"],["studio.html","Темы","studio"],["settings.html","Настройки","settings"]];
const ICONS={"home": "<circle cx=\"12\" cy=\"12\" r=\"8\"/><circle cx=\"12\" cy=\"12\" r=\"3\"/><path d=\"M12 2v2m0 16v2M2 12h2m16 0h2\"/>", "chat": "<path d=\"M20 10a8 8 0 0 1-8 8 9 9 0 0 1-4-.9L3 19l1.8-4.5A8 8 0 1 1 20 10Z\"/><path d=\"M8 10h8M8 13h5\"/>", "training": "<path d=\"m2 9 10-5 10 5-10 5-10-5Zm4 2v5q6 5 12 0v-5M22 9v7\"/>", "models": "<path d=\"m12 2 9 5v10l-9 5-9-5V7zM3 7l9 5 9-5M12 12v10\"/>", "memory": "<ellipse cx=\"12\" cy=\"5\" rx=\"8\" ry=\"3\"/><path d=\"M4 5v7c0 4 16 4 16 0V5M4 12v7c0 4 16 4 16 0v-7\"/>", "system": "<path d=\"M2 12h4l3-7 5 14 3-7h5\"/><path d=\"M4 4h16v16H4z\"/>", "projects": "<path d=\"M3 3h8v8H3zM13 3h8v6h-8zM13 11h8v10h-8zM3 13h8v8H3z\"/>", "cinema": "<rect x=\"3\" y=\"8\" width=\"18\" height=\"13\" rx=\"2\"/><path d=\"M3 8V3h18v5M7 3l-3 5M13 3 9 8M19 3l-4 5M10 12l5 3-5 3z\"/>", "install": "<path d=\"M12 2v13m-4-4 4 4 4-4M4 16v5h16v-5\"/>", "settings": "<circle cx=\"12\" cy=\"12\" r=\"3\"/><path d=\"m12 2 2 3 3-1 2 3-2 3 2 2-2 3 2 3-3 2-3-2-3 2-3-2 2-3-2-3 2-2-2-3 2-3 3 1z\"/>", "studio": "<path d=\"m12 2 2.2 7.8L22 12l-7.8 2.2L12 22l-2.2-7.8L2 12l7.8-2.2z\"/>", "dispatcher": "<rect x=\"2\" y=\"4\" width=\"7\" height=\"6\" rx=\"1\"/><rect x=\"15\" y=\"4\" width=\"7\" height=\"6\" rx=\"1\"/><rect x=\"8\" y=\"16\" width=\"8\" height=\"6\" rx=\"1\"/><path d=\"M5.5 10v3h13v-3M12 13v3\"/>", "downloads": "<path d=\"M12 2v14m-5-5 5 5 5-5M3 16v5h18v-5\"/>"};
function boot(){
 if(D.getElementById('noxSharedHeaderV10'))return;
 const path=location.pathname.toLowerCase();
 const prefix=rootURL;
 const header=D.createElement('header');header.id='noxSharedHeaderV10';header.className='nox-shared-header-v10';
 header.setAttribute('aria-label','Единая навигация NOX HELION');
 const brand=D.createElement('a');brand.href=prefix+'index.html';brand.className='nox-shared-signature-v10';brand.setAttribute('aria-label','NOX HELION · на главную');
 brand.innerHTML='<span class="nox-signature-eclipse-v10" aria-hidden="true">◉</span><span class="nox-signature-text-v10">NOX</span>';header.appendChild(brand);
 const nav=D.createElement('nav');nav.className='nox-shared-links-v10';nav.setAttribute('aria-label','Все разделы NOX — только графические ссылки');
 let active=null;
 for(const [url,title,kind] of ROUTES){
   const a=D.createElement('a');a.href=prefix+url;a.title=title;a.setAttribute('aria-label',title);a.dataset.noxNavKind=kind;
   if(path.endsWith('/'+url)||path.endsWith('/pc/'+url)||path.includes('/pc/pages/'+kind+'/')||(kind==='home'&&path.endsWith('/pc/home-v18.html'))||(kind==='chat'&&path.endsWith('/pc/resonance.html'))){a.setAttribute('aria-current','page');active=a}
   a.innerHTML='<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'+(ICONS[kind]||ICONS.system)+'</svg><span>'+title+'</span>';
   nav.appendChild(a);
 }
 header.appendChild(nav);
 // Reuse HOME's real function-catalog action; the extra control only exists where its actual handler exists.
 const nativeCatalog=D.querySelector('[data-nox-catalog-open]');
 if(nativeCatalog){
   const catalog=D.createElement('button');catalog.type='button';catalog.className='nox-shared-catalog-v11';
   catalog.setAttribute('aria-label','Все функции NOX');catalog.title='Все функции NOX';
   catalog.innerHTML='<svg viewBox="0 0 24 24" width="19" height="19" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg><span>Функции</span>';
   catalog.addEventListener('click',()=>nativeCatalog.click());header.appendChild(catalog);
 }
 B.prepend(header);
 // Preserve existing native menus and their handlers in source; no separate sidebar is shown when its routes are in the common header.
 B.classList.add('nox-shared-ui-ready-v10');H.dataset.noxUnifiedV10='1';
 // Duplicate older V9 floating menu cannot obscure the common header.
 const old=D.getElementById('noxV9Nav');if(old)old.hidden=true;
 if(active && nav.scrollWidth>nav.clientWidth){nav.scrollLeft=Math.max(0,active.offsetLeft-nav.offsetLeft-(nav.clientWidth-active.clientWidth)/2);}
 D.addEventListener('click',ev=>{const el=ev.target.closest?.('#nx-menu');if(el){ev.preventDefault();ev.stopImmediatePropagation();const nav=D.querySelector('.nox-shared-links-v10');nav?.focus?.();nav?.querySelector('a[aria-current="page"]')?.focus();}},true);
}
if(D.readyState==='loading')D.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
window.NOX_SHARED_UI_V10=Object.freeze({version:'11.0',routes:ROUTES.length,header:'one canonical HOME navigation',noDropdowns:true});
})();