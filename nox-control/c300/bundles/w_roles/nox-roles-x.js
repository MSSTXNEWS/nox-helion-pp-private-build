/* NOX roles-x (WEB): плитки ролей студии + медиа-панель (wavesurfer для звука, нативный video для ролика). Готовое: nox-studio-roles, wavesurfer, Shoelace. Генерация видео/музыки: HOLD, пока сервис не подключён. Откат: ?rx=0 */
(function(){
if(/[?&]rx=0/.test(location.search))return;
var rid=new URLSearchParams(location.search).get('role')||'writer';
function esc(s){return String(s).replace(/[&<>"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})}
var css=document.createElement('style');css.textContent='#rsRoot{--rs-h:calc(100vh / var(--rs-z) - 214px)!important}#rs-ch-h>*:not(sl-icon):not(b){display:none!important}#rs-ch-h b{font-size:14px}#rx-tiles{display:flex;gap:8px;flex-wrap:wrap;margin:0 0 12px}#rx-tiles a{min-height:44px;display:inline-flex;align-items:center;gap:8px;padding:0 16px;border-radius:12px;border:1px solid var(--gx-5,#2a2c30);background:var(--gx-3,#18191b);color:var(--gx-12,#edeef0);text-decoration:none;font-size:14px;font-weight:600}#rx-tiles a[aria-current=page]{border-color:var(--gx-acc,#c8b6a2);background:color-mix(in srgb,var(--gx-acc,#c8b6a2) 14%,var(--gx-3,#18191b))}#rx-tiles a:focus-visible{outline:2px solid #9db1d1;outline-offset:2px}#rs-media{border-top:1px solid var(--gx-5,#2a2c30);padding:12px 14px;display:flex;flex-direction:column;gap:10px}#rs-media .rx-r{display:flex;gap:8px;flex-wrap:wrap;align-items:center}#rs-media video{width:100%;max-height:260px;border-radius:12px;background:#000}#rx-wave{min-height:72px;border-radius:12px;background:var(--gx-2,#111113)}#rs-media .rx-hold{font-size:13px;color:var(--gx-11,#b0b4ba);margin:0}.rx-b{display:inline-block}';document.head.appendChild(css);
function tiles(cfg){var page=document.getElementById('rsRoot');if(!page||document.getElementById('rx-tiles'))return;var n=document.createElement('nav');n.id='rx-tiles';n.setAttribute('aria-label','Роли студии');
 Object.keys(cfg.roles).forEach(function(k){var r=cfg.roles[k];if(r.soon)return;var a=document.createElement('a');a.href='?role='+k;a.innerHTML='<sl-icon library="tabler" name="'+esc(r.icon||'point')+'" aria-hidden="true"></sl-icon>'+esc(r.title);if(k===rid)a.setAttribute('aria-current','page');n.appendChild(a)});page.parentNode.insertBefore(n,page)}
function media(){var cv=document.getElementById('rs-cv');if(!cv||document.getElementById('rs-media'))return;
 if(rid!=='music'&&rid!=='video'&&rid!=='cinema')return;
 var m=document.createElement('div');m.id='rs-media';var inp=document.createElement('input');inp.type='file';inp.hidden=true;inp.setAttribute('aria-label','Выбрать файл');
 var pick=document.createElement('sl-button');pick.textContent=rid==='music'?'Открыть аудиофайл':'Открыть видеофайл';var row=document.createElement('div');row.className='rx-r';row.appendChild(pick);m.appendChild(row);m.appendChild(inp);
 var hold=document.createElement('p');hold.className='rx-hold';hold.textContent=rid==='music'?'Генерация музыки: HOLD, генератор не подключён. Здесь можно прослушать свой файл и писать текст и промпты.':rid==='video'?'Генерация видео: HOLD, генератор не подключён. Здесь можно смотреть свой ролик и писать сценарий и промпты.':'Файл смотрится локально в браузере, никуда не отправляется.';m.appendChild(hold);
 cv.appendChild(m);pick.addEventListener('click',function(){inp.click()});
 inp.accept=rid==='music'?'audio/*':'video/*';
 inp.addEventListener('change',function(){var f=inp.files[0];if(!f)return;var u=URL.createObjectURL(f);m.querySelectorAll('.rx-med').forEach(function(x){x.remove()});
  if(rid==='music'){var w=document.createElement('div');w.id='rx-wave';w.className='rx-med';m.insertBefore(w,hold);var pp=document.createElement('sl-button');pp.className='rx-med';pp.setAttribute('variant','primary');pp.textContent='Играть / пауза';row.appendChild(pp);
   import('./vendor/wavesurfer.js/dist/wavesurfer.esm.js').then(function(M){var WS=M.default||M;var ws=WS.create({container:w,url:u,waveColor:'#7b8794',progressColor:'#9db1d1',height:72});pp.addEventListener('click',function(){ws.playPause()})}).catch(function(){w.textContent='Не удалось загрузить wavesurfer'})}
  else{var v=document.createElement('video');v.className='rx-med';v.controls=true;v.src=u;v.setAttribute('aria-label','Видео');m.insertBefore(v,hold)}})}

/* Учёный: KaTeX (vendor) для формул в просмотре и ответах; поиск источников: HOLD, пока API поиска NOX не подключён */
function sci(){if(rid!=='scientist')return;
 var l=document.createElement('link');l.rel='stylesheet';l.href='./vendor/katex/katex.min.css';document.head.appendChild(l);
 function sc(u){return new Promise(function(ok,no){var e=document.createElement('script');e.src=u;e.onload=ok;e.onerror=no;document.head.appendChild(e)})}
 sc('./vendor/katex/katex.min.js').then(function(){return sc('./vendor/katex/auto-render.min.js')}).then(function(){
  var D=[{left:'$$',right:'$$',display:true},{left:'\\(',right:'\\)',display:false},{left:'\\[',right:'\\]',display:true},{left:'$',right:'$',display:false}];var t=0;
  function run(){['#rs-pvb','#rs-f'].forEach(function(q){var e=document.querySelector(q);if(e&&window.renderMathInElement){try{window.renderMathInElement(e,{delimiters:D,throwOnError:false})}catch(x){}}})}
  new MutationObserver(function(){clearTimeout(t);t=setTimeout(run,400)}).observe(document.body,{childList:true,subtree:true});run()}).catch(function(){});
 var n=0,iv=setInterval(function(){var cv=document.getElementById('rs-cv');if(cv&&!document.getElementById('rs-media')){clearInterval(iv);var m=document.createElement('div');m.id='rs-media';var p=document.createElement('p');p.className='rx-hold';p.textContent='Поиск источников: HOLD, поисковый API NOX не подключён. Источники вставляйте сами (DOI, ссылки); формулы в записи $...$ и $$...$$ отображаются в «Просмотре» и в ответах. Ничего не выдумываю: нет данных, значит HOLD.';m.appendChild(p);cv.appendChild(m)}if(++n>40)clearInterval(iv)},300)}
function go(){sci();fetch('./roles.json?v='+Date.now()).then(function(r){return r.json()}).then(function(c){tiles(c)}).catch(function(){});var n=0,iv=setInterval(function(){media();if(document.getElementById('rs-media')||++n>40||['music','video','cinema'].indexOf(rid)<0)clearInterval(iv)},300)}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',go);else go();
})();
