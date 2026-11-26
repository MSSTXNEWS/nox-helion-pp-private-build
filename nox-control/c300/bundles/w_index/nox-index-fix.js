/* NOX index-fix (WEB): неразрушающий слой для главной (эталон V29.3 не меняется): относительные api/ -> /api/ (убирает 404), доступность (h1, баннер, подписи), цели касания 44 px только через CSS. Откат: ?ixfix=0 */
(function(){
if(/[?&]ixfix=0/.test(location.search))return;
try{var of=window.fetch;if(of){window.fetch=function(u,o){try{var s=typeof u==='string'?u:(u&&u.href)||(u&&u.url)||'',n=s;if(/^(\.\/)?api\//.test(s))n='/'+s.replace(/^\.\//,'');else if(/^(https?:\/\/[^\/]+)?\/web\/api\//.test(s))n=s.replace(/\/web\/api\//,'/api/');if(n!==s&&typeof u!=='object'||(n!==s&&u instanceof URL))return of.call(this,n,o);if(n!==s&&u&&u.url)return of.call(this,n,o||{method:u.method,headers:u.headers})}catch(e){}return of.call(this,u,o)}}}catch(e){}
try{var ox=XMLHttpRequest.prototype.open;XMLHttpRequest.prototype.open=function(m,u){try{if(typeof u==='string'){if(/^(\.\/)?api\//.test(u))arguments[1]='/'+u.replace(/^\.\//,'');else if(/\/web\/api\//.test(u))arguments[1]=u.replace(/\/web\/api\//,'/api/')}}catch(e){}return ox.apply(this,arguments)}}catch(e){}
var st=document.createElement('style');st.textContent='.nox-shared-signature-v10,#nox-cinematic-light-cycle,.nox-graphic-control{min-height:44px;min-width:44px;box-sizing:border-box}#noxSharedHeaderV10 a,.nox-shared-nav a{min-height:44px;box-sizing:border-box}.nx-sr-h1{position:absolute!important;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}';
(document.head||document.documentElement).appendChild(st);
function fix(){
 var h=document.getElementById('noxSharedHeaderV10');if(h&&h.getAttribute('role')!=='group'&&document.querySelectorAll('header').length>1)h.setAttribute('role','group');
 document.querySelectorAll('a[aria-label],button[aria-label]').forEach(function(a){var t=(a.textContent||'').trim(),l=a.getAttribute('aria-label')||'';if(t&&l.toLowerCase().indexOf(t.toLowerCase())<0&&!a.dataset.nxl){a.dataset.nxl=1;a.setAttribute('aria-label',t+': '+l)}});
 var vh=[].slice.call(document.querySelectorAll('h1')).some(function(x){var r=x.getBoundingClientRect();return r.width>0&&getComputedStyle(x).visibility!=='hidden'});if(!vh&&!document.querySelector('.nx-sr-h1')&&document.body){var e=document.createElement('h1');e.className='nx-sr-h1';e.textContent='NOX HELION — Резонанс';var host=document.querySelector('main,[role=main],[role=banner],body>header:not(#noxSharedHeaderV10)')||document.getElementById('noxSharedHeaderV10')||document.body;host.insertBefore(e,host.firstChild)}
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',fix);else fix();new MutationObserver(function(){clearTimeout(window.__nxif);window.__nxif=setTimeout(fix,300)}).observe(document.documentElement,{childList:true,subtree:true});setTimeout(fix,2500)
})();
