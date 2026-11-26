/* NOX index-fix (WEB): неразрушающий слой для главной (эталон V29.3 не меняется): относительные api/ -> /api/ (убирает 404), доступность (h1, баннер, подписи), цели касания 44 px только через CSS. Откат: ?ixfix=0 */
(function(){
if(/[?&]ixfix=0/.test(location.search))return;
try{var of=window.fetch;if(of){window.fetch=function(u,o){try{if(typeof u==='string'&&/^(\.\/)?api\//.test(u))u='/'+u.replace(/^\.\//,'');else if(typeof u==='string'&&/^\/web\/api\//.test(u))u=u.replace(/^\/web/,'')}catch(e){}return of.call(this,u,o)}}}catch(e){}
var st=document.createElement('style');st.textContent='.nox-shared-signature-v10,#nox-cinematic-light-cycle,.nox-graphic-control{min-height:44px;min-width:44px;box-sizing:border-box}#noxSharedHeaderV10 a,.nox-shared-nav a{min-height:44px;box-sizing:border-box}.nx-sr-h1{position:absolute!important;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}';
(document.head||document.documentElement).appendChild(st);
function fix(){
 var h=document.getElementById('noxSharedHeaderV10');if(h&&h.getAttribute('role')!=='navigation'&&document.querySelectorAll('header').length>1)h.setAttribute('role','navigation');
 document.querySelectorAll('a[aria-label]').forEach(function(a){var t=(a.textContent||'').trim(),l=a.getAttribute('aria-label')||'';if(t&&l.toLowerCase().indexOf(t.toLowerCase())<0&&!a.dataset.nxl){a.dataset.nxl=1;a.setAttribute('aria-label',t+': '+l)}});
 if(!document.querySelector('h1')&&document.body){var e=document.createElement('h1');e.className='nx-sr-h1';e.textContent='NOX HELION — Резонанс';document.body.insertBefore(e,document.body.firstChild)}
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',fix);else fix();new MutationObserver(function(){clearTimeout(window.__nxif);window.__nxif=setTimeout(fix,300)}).observe(document.documentElement,{childList:true,subtree:true});setTimeout(fix,2500)
})();
