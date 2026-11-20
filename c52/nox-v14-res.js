/* V14.9 «Резонанс» — C11 мир/палитра по страницам, C18 импорт чата, C23 сворачиваемое меню, C24 индикатор связи, C25 последняя синхронизация, C29 подсказки клавиш */
(()=>{'use strict';if(window.NOX_V14_RES)return;window.NOX_V14_RES=1;
const D=document,H=D.documentElement;
const ls={get(k,d){try{const v=JSON.parse(localStorage.getItem(k)||'null');return v??d}catch{return d}},set(k,v){try{localStorage.setItem(k,JSON.stringify(v))}catch{}}};
const el=(t,c,h)=>{const e=D.createElement(t);if(c)e.className=c;if(h!=null)e.innerHTML=h;return e};
const toast=(t,k,ms)=>{try{window.NoxToast&&window.NoxToast(t,k,ms)}catch{}};
const W=()=>window.NOX_CINEMATIC_WORLDS;
const mq=q=>{try{return matchMedia(q)}catch{return{matches:false,addEventListener(){}}}};
const FINE=mq('(hover: hover) and (pointer: fine)'),MOB=mq('(max-width: 760px)');
const PAGE=(location.pathname.replace(/\/index\.html$/,'/').replace(/\/+$/,'/'))||'/';

/* ---------- C11: мир и палитра для каждой страницы ---------- */
const WPK='nox.res.wp.'+PAGE;let wpLast=null,wpReady=false;
function wpSave(){const w=W();if(!w?.getState||!wpReady)return;const s=w.getState();if(!s?.world||!s?.palette)return;const k=s.world+'|'+s.palette;if(k===wpLast)return;wpLast=k;ls.set(WPK,{world:s.world,palette:s.palette,ts:Date.now()})}
function wpInit(tries=0){const w=W();if(!w?.getState){if(tries<40)setTimeout(()=>wpInit(tries+1),250);return}
 if(!w.__nxr){w.__nxr=1;for(const f of ['setWorld','setPalette']){const o=w[f];if(typeof o==='function')w[f]=function(){const r=o.apply(this,arguments);setTimeout(wpSave,0);return r}}}
 const saved=ls.get(WPK,null),s=w.getState();
 if(saved&&w.worlds?.includes(saved.world)&&w.palettes?.includes(saved.palette)&&(s.world!==saved.world||s.palette!==saved.palette)){
  try{if(s.world!==saved.world)w.setWorld(saved.world);if(w.getState().palette!==saved.palette)w.setPalette(saved.palette)}catch{}}
 const n=w.getState();wpLast=n.world+'|'+n.palette;wpReady=true;setInterval(wpSave,2000)}

/* ---------- настройки ---------- */
const pref={bar:ls.get('nox.res.barmin',false)};
const setPref=(k,v,key)=>{pref[k]=v;ls.set(key,v)};

/* ---------- C18: импорт чата ---------- */
const IMPK='nox.res.import';
function normalize(j){const arr=Array.isArray(j)?j:Array.isArray(j?.messages)?j.messages:null;if(!arr)return null;
 return arr.map(m=>{if(!m||typeof m!=='object')return null;const role=String(m.role||'').toLowerCase();let t=m.text??m.content;if(Array.isArray(t))t=t.map(x=>typeof x==='string'?x:x?.text||'').join('\n');if(typeof t!=='string')return null;t=t.trim();if(!t)return null;return{role:/^(user|me|human|вы)$/.test(role)?'user':'nox',text:t.slice(0,20000)}}).filter(Boolean).slice(0,500)}
function renderImport(list,name){const box=D.getElementById('messages');if(!box)return false;
 const sep=el('div','nxr-imp-sep');sep.setAttribute('role','note');sep.textContent=`Импорт · ${name||'файл'} · ${list.length} сообщ. · только для просмотра, на сервер не отправлялось`;box.append(sep);
 for(const m of list){const a=el('article','msg '+(m.role==='user'?'me':'nox')+' nxr-imported');a.dataset.nxrImport='1';const l=el('label');l.textContent=(m.role==='user'?'ВЫ':'NOX HELION')+' · импорт';const t=el('div');t.textContent=m.text;a.append(l,t);box.append(a)}
 sep.scrollIntoView({block:'start'});return true}
function importData(j,name){const list=normalize(j);if(!list||!list.length){toast('Файл не похож на экспорт чата NOX ([{role,text}] или [{role,content}])','warn',2600);return 0}
 if(renderImport(list,name)){toast('Импортировано сообщений: '+list.length,'ok',1800);return list.length}
 try{sessionStorage.setItem(IMPK,JSON.stringify({name,list}))}catch{toast('Файл слишком большой','warn',2000);return 0}
 toast('Открываю чат для показа импорта…','info',1500);const p=location.pathname;location.href=(p.includes('/pc/pages/')?'../../':'')+'chat.html';return list.length}
function importChat(){const i=el('input');i.type='file';i.accept='.json,application/json';i.hidden=true;i.className='nxr-file';D.body.append(i);
 i.onchange=()=>{const f=i.files?.[0];i.remove();if(!f)return;if(f.size>8e6){toast('Файл больше 8 МБ','warn',2000);return}
  f.text().then(s=>{let j;try{j=JSON.parse(s)}catch{toast('Не удалось прочитать JSON','warn',2000);return}importData(j,f.name)}).catch(()=>toast('Не удалось открыть файл','warn',2000))};
 i.click()}
function pendingImport(){let p;try{p=JSON.parse(sessionStorage.getItem(IMPK)||'null')}catch{}if(!p)return;if(renderImport(p.list||[],p.name)){sessionStorage.removeItem(IMPK);toast('Импортировано сообщений: '+(p.list||[]).length,'ok',1800)}}

/* ---------- C23: сворачиваемое меню оболочки (#noxV14Bar) ---------- */
let tog=null,mini=null;
function barApply(){const b=D.getElementById('noxV14Bar');H.toggleAttribute('data-nxr-bar-min',!!pref.bar);if(mini)mini.hidden=!pref.bar;if(tog){tog.setAttribute('aria-expanded',String(!pref.bar))}
 if(b&&!b.classList.contains('nv-inline'))D.body.style.paddingBottom=pref.bar?'':(b.offsetHeight+22)+'px'}
function barToggle(v){setPref('bar',v==null?!pref.bar:!!v,'nox.res.barmin');barApply();(pref.bar?mini:tog)?.focus?.({preventScroll:true})}
function barMount(){const b=D.getElementById('noxV14Bar');if(!b||b.querySelector('.nxr-bartog'))return!!b;
 tog=el('button','nv-btn nxr-bartog','<span aria-hidden="true">▾</span>');tog.type='button';tog.title='Свернуть меню';tog.setAttribute('aria-label','Свернуть меню NOX');tog.setAttribute('aria-controls','noxV14Bar');tog.onclick=()=>barToggle(true);b.append(tog);
 mini=el('button','nxr-barmini','<span aria-hidden="true">▴</span>');mini.type='button';mini.title='Развернуть меню';mini.setAttribute('aria-label','Развернуть меню NOX');mini.setAttribute('aria-controls','noxV14Bar');mini.hidden=true;mini.onclick=()=>barToggle(false);D.body.append(mini);
 barApply();return true}
let lastY=scrollY;addEventListener('scroll',()=>{const y=scrollY;if(!MOB.matches){H.removeAttribute('data-nxr-bar-away');lastY=y;return}if(Math.abs(y-lastY)<24)return;H.toggleAttribute('data-nxr-bar-away',y>lastY&&y>80);lastY=y},{passive:true});

/* ---------- C24 + C25: связь и синхронизация ---------- */
let net=null,sync=null,ownOk=0,lastCheck=0,checking=false;
function netMount(){const s=D.getElementById('nvStatus');if(!s||D.querySelector('.nxr-net'))return;
 net=el('span','nxr-net','<b class="nxr-dot" aria-hidden="true"></b><span>проверка…</span>');net.setAttribute('role','status');net.dataset.state='idle';net.title='Связь с сервером NOX: GET /api/health раз в 30 с';
 sync=el('span','nxr-sync','синхр.: Н/Д');sync.title='Время последнего успешного ответа /api/*';s.after(net,sync);syncDraw()}
function netSet(state,txt){if(!net)return;net.dataset.state=state;net.querySelector('span').textContent=txt;net.setAttribute('aria-label','Связь: '+txt)}
async function check(){if(checking)return;checking=true;lastCheck=Date.now();const t0=performance.now();let ctl,tm;
 try{ctl=new AbortController();tm=setTimeout(()=>ctl.abort(),8000);const r=await fetch('/api/health',{cache:'no-store',signal:ctl.signal});const ms=Math.round(performance.now()-t0);
  if(r.ok){ownOk=Date.now();netSet(ms>2000?'slow':'ok',ms+' мс')}else netSet('down','нет связи · '+r.status)}
 catch{netSet('down','нет связи')}finally{clearTimeout(tm);checking=false;syncDraw()}}
function syncDraw(){if(!sync)return;const t=Math.max(+window.NOX_LAST_OK||0,ownOk);if(!t){sync.textContent='синхр.: Н/Д';sync.dataset.ok='0';return}
 const d=new Date(t),p=n=>String(n).padStart(2,'0');sync.textContent='синхр.: '+p(d.getHours())+':'+p(d.getMinutes())+':'+p(d.getSeconds());sync.dataset.ok='1';sync.title='Последний успешный ответ /api/*: '+Math.round((Date.now()-t)/1000)+' с назад'}
setInterval(()=>{if(!D.hidden&&net&&Date.now()-lastCheck>=29000)check()},5000);
setInterval(syncDraw,5000);
D.addEventListener('visibilitychange',()=>{if(!D.hidden&&net&&Date.now()-lastCheck>=30000)check()});

/* ---------- C29: подсказки горячих клавиш ---------- */
const WN=['HELION','CHRONOS','SOMNIUM','FORGE','SYNAPSE'],CN=['Золото','Медь','Ледяной','Ионный','Аметист','Платина'];
const ROWKEYS={'О сборке':['I','I'],'Высокий контраст':['H','H'],'Полный экран':['F','F'],'Горячие клавиши':['?','?'],'Режим презентации':['P','P'],'Текст крупнее':[']',']'],'Текст мельче':['[','[']};
function mark(e,label,aria){if(!e||e.dataset.nxrKey===label)return;e.dataset.nxrKey=label;e.setAttribute('aria-keyshortcuts',aria);const t=e.getAttribute('title')||'';if(!t.includes(label))e.setAttribute('title',(t||e.textContent.trim().replace(/\s+/g,' ')).replace(/\s*\(.*\)$/,'')+' ('+label+')')}
function keysBar(){const b=D.getElementById('noxV14Bar');if(!b)return;mark(b.querySelector('[data-nv=search]'),'Ctrl K','Control+K Meta+K');mark(b.querySelector('[data-nv=cmd]'),'Ctrl K','Control+K Meta+K');mark(b.querySelector('[data-nv=assist]'),'Ctrl J','Control+J Meta+J');mark(D.querySelector('.nv-fab'),'Ctrl J','Control+J Meta+J');mark(D.querySelector('.nv-pal-in kbd'),'Esc','Escape')}
function keysPal(list){const w=W();list.querySelectorAll('.nv-row').forEach(r=>{const t=(r.querySelector('span')?.textContent||'').trim();
 if(ROWKEYS[t])return mark(r,ROWKEYS[t][0],ROWKEYS[t][1]);
 let m=t.match(/^Мир · (.+)$/);if(m){const i=w?.worlds?w.worlds.indexOf(m[1].toLowerCase()):WN.indexOf(m[1]);if(i>=0&&i<5)mark(r,String(i+1),String(i+1));return}
 m=t.match(/^Цвет · (.+)$/);if(m){const i=CN.indexOf(m[1]);if(i>=0)mark(r,'Shift '+(i+1),'Shift+'+(i+1))}})}
let kb=null;
function kbShow(e){const t=e.target.closest?.('[data-nxr-key]');if(!t||!FINE.matches)return;kb=kb||D.body.appendChild(el('kbd','nxr-kbd'));kb.setAttribute('aria-hidden','true');kb.textContent=t.dataset.nxrKey;kb.hidden=false;const r=t.getBoundingClientRect();
 const w=kb.offsetWidth,h=kb.offsetHeight;let x=Math.min(innerWidth-w-4,Math.max(4,r.right-w/2-6)),y=r.top-h-4;if(y<4)y=r.bottom+4;kb.style.left=x+'px';kb.style.top=y+'px'}
D.addEventListener('pointerover',kbShow,{passive:true});D.addEventListener('focusin',e=>{if(e.target.matches?.(':focus-visible'))kbShow(e)});
D.addEventListener('pointerout',e=>{if(kb&&e.target.closest?.('[data-nxr-key]'))kb.hidden=true},{passive:true});D.addEventListener('focusout',()=>{if(kb)kb.hidden=true});
addEventListener('scroll',()=>{if(kb)kb.hidden=true},{passive:true,capture:true});

/* ---------- пункты Ctrl+K ---------- */
function items(){return[
 ['Импорт чата из JSON','.json',importChat],
 [(pref.bar?'Развернуть':'Свернуть')+' меню NOX','меню',()=>barToggle()],
 ['Проверить связь с сервером','/api/health',()=>check()]]}
function hookPalette(){const p=D.querySelector('.nv-pal');if(!p||p.dataset.nxr)return;p.dataset.nxr='1';
 new MutationObserver(()=>{if(p.hidden)return;const list=p.querySelector('#nvList');if(!list)return;keysPal(list);
  if(list.querySelector('.nxr-grp')||p.querySelector('#nvQ')?.value)return;list.append(el('div','nv-grp nxr-grp','Резонанс'));
  items().forEach(([t,d,f])=>{const b=el('button','nv-row nxr-row');b.type='button';const s1=el('span'),s2=el('small');s1.textContent=t;s2.textContent=d;b.append(s1,s2);b.onclick=()=>{p.hidden=true;f()};list.append(b)})}).observe(p,{attributes:true,attributeFilter:['hidden'],childList:true,subtree:true})}

/* ---------- старт ---------- */
function start(){if(!D.body)return;hookPalette();barMount();netMount();keysBar();pendingImport();if(net&&!lastCheck&&!D.hidden)check()}
if(D.readyState!=='loading')start();else D.addEventListener('DOMContentLoaded',start);
setTimeout(start,1200);setTimeout(start,3200);
wpInit();
window.NoxRes={importChat,importData,check,toggleBar:barToggle,state:()=>({...pref,page:PAGE,saved:ls.get(WPK,null),net:net?.dataset.state||null,lastOk:Math.max(+window.NOX_LAST_OK||0,ownOk)||null})};
})();
