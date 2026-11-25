/* U: «листок блокнота» — постоянная правая панель на всех страницах. Редактор: CodeMirror 5 из vendor (простой режим). Автосохранение, листы по датам, поиск, голос, «→ NOX» (заметки + память), «→ Доска» (стикер Excalidraw).
   Хоткей N / Cmd+Shift+N. API: NOXNote.add(text,{to:'pad'|'nox'|'board'|'both'}), open(), toggle(), search(q). Цвета только через переменные темы (--ds-*). */
(function(){ if(window.NOXNote)return;
 const K='nox.pad.v1',BK='nox.s2.board';
 const today=()=>{const d=new Date();return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0')};
 let S;try{S=JSON.parse(localStorage.getItem(K)||'{}')}catch(e){S={}}
 S.sheets=S.sheets||{};S.ts=S.ts||{};S.w=S.w||320;S.open=!!S.open;S.cur=S.cur||today();S.proj=S.proj||{};
 const save=()=>{try{localStorage.setItem(K,JSON.stringify(S))}catch(e){}};
 const esc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
 let root,cm,ta,tab,saved=0,rec=null;
 const CSS=`
#u-pad{--w:320px;position:fixed;top:64px;bottom:calc(var(--ds-dock-h,48px) + 8px);right:0;width:var(--w);max-width:92vw;z-index:8000;display:flex;flex-direction:column;color:var(--ds-ink,#e6e7ea);font-family:inherit;font-size:15px;transform:translateX(0);transition:transform .25s ease;border-radius:14px 0 0 14px;border:1px solid var(--ds-line,rgba(255,255,255,.14));border-right:0;box-shadow:-10px 0 40px rgba(0,0,0,.35);overflow:hidden;
 background:linear-gradient(180deg,color-mix(in srgb,var(--ds-ink,#e6e7ea) 7%,var(--ds-bg,#25272b)),color-mix(in srgb,var(--ds-ink,#e6e7ea) 3%,var(--ds-bg,#25272b)));backdrop-filter:blur(14px)}
#u-pad:before{content:"";position:absolute;inset:0;pointer-events:none;opacity:.05;background-image:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='160' height='160'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='2'/></filter><rect width='100%' height='100%' filter='url(%23n)'/></svg>")}
#u-pad.shut{transform:translateX(calc(100% - 0px));box-shadow:none}
#u-tab{position:fixed;right:0;top:50%;transform:translateY(-50%);z-index:7999;min-width:28px;min-height:96px;padding:8px 4px;border-radius:12px 0 0 12px;border:1px solid var(--ds-line,rgba(255,255,255,.18));border-right:0;background:color-mix(in srgb,var(--ds-ink,#e6e7ea) 10%,var(--ds-bg,#25272b));color:var(--ds-ink,#e6e7ea);cursor:pointer;writing-mode:vertical-rl;font-size:14px;letter-spacing:.08em}
#u-tab:focus-visible,#u-pad :focus-visible{outline:2px solid var(--ds-acc,#9aa3b2);outline-offset:2px}
#u-pad.open~#u-tab{display:none}
#u-grip{position:absolute;left:0;top:0;bottom:0;width:8px;cursor:col-resize;z-index:2}#u-grip:hover{background:color-mix(in srgb,var(--ds-acc,#9aa3b2) 30%,transparent)}
.up-h{position:relative;z-index:1;display:flex;align-items:center;gap:4px;padding:6px 8px 6px 14px;border-bottom:1px solid var(--ds-line,rgba(255,255,255,.14))}
.up-h b{flex:1;font-size:15px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.up-p{position:relative;z-index:1;display:flex;gap:6px;align-items:center;padding:6px 14px;font-size:14px;opacity:.9}
.up-p input{flex:1;min-width:0;min-height:44px;background:transparent;border:0;border-bottom:1px dashed var(--ds-line,rgba(255,255,255,.25));color:inherit;font:inherit}
#u-pad button{min-width:44px;min-height:44px;border-radius:10px;border:1px solid transparent;background:transparent;color:inherit;cursor:pointer;font:inherit;font-size:14px;display:inline-flex;align-items:center;justify-content:center;gap:4px}
#u-pad button:hover{background:color-mix(in srgb,var(--ds-ink,#e6e7ea) 10%,transparent)}
#u-pad .up-go{background:color-mix(in srgb,var(--ds-acc,#9aa3b2) 22%,transparent);border-color:color-mix(in srgb,var(--ds-acc,#9aa3b2) 55%,transparent);padding:0 10px}
.up-ed{position:relative;z-index:1;flex:1;min-height:0;display:flex}
.up-ed .CodeMirror{flex:1;height:100%;background:transparent;color:inherit;font:inherit;font-size:16px;line-height:28px;padding-left:34px;
 background-image:repeating-linear-gradient(to bottom,transparent 0,transparent 27px,color-mix(in srgb,var(--ds-ink,#e6e7ea) 12%,transparent) 27px,color-mix(in srgb,var(--ds-ink,#e6e7ea) 12%,transparent) 28px);background-attachment:local}
.up-ed .CodeMirror:before{content:"";position:absolute;left:26px;top:0;bottom:0;width:1px;background:color-mix(in srgb,var(--ds-acc,#9aa3b2) 45%,transparent);z-index:3}
.up-ed .CodeMirror-lines{padding:6px 0}.up-ed .CodeMirror pre{padding:0 12px 0 8px;line-height:28px}.up-ed .CodeMirror-cursor{border-left:2px solid var(--ds-acc,#9aa3b2)}
.up-ed .CodeMirror-selected{background:color-mix(in srgb,var(--ds-acc,#9aa3b2) 35%,transparent)!important}.up-ed .CodeMirror-gutters{display:none}
.up-ed textarea.up-raw{flex:1;background:transparent;border:0;color:inherit;font:inherit;font-size:16px;line-height:28px;padding:6px 12px 6px 34px;resize:none}
.up-f{position:relative;z-index:1;display:flex;flex-wrap:wrap;gap:4px;align-items:center;padding:6px 8px;border-top:1px solid var(--ds-line,rgba(255,255,255,.14));font-size:13px}
.up-f .st{margin-left:auto;opacity:.7}
.up-s{position:relative;z-index:1;max-height:40%;overflow:auto;padding:4px 14px;border-bottom:1px solid var(--ds-line,rgba(255,255,255,.14))}
.up-s button{display:block;width:100%;justify-content:flex-start;text-align:left;font-size:14px;padding:6px 8px}
@media(max-width:768px){#u-pad{top:56px;width:min(92vw,420px)!important}}
@media (prefers-reduced-motion:reduce){#u-pad{transition:none}}`;
 /* ---- хранилище листов ---- */
 const sheet=()=>S.sheets[S.cur]||'';
 function setSheet(t){S.sheets[S.cur]=t;S.ts[S.cur]=Date.now()/1000;save();push()}
 function dates(){return Object.keys(S.sheets).filter(function(d){return S.sheets[d]&&S.sheets[d].trim()}).sort()}
 function head(){const el=root.querySelector('.up-h b');el.textContent=S.cur===today()?'Сегодня · '+S.cur:S.cur;root.querySelector('.up-p input').value=S.proj[S.cur]||''}
 function load(d){S.cur=d;save();window.__upSilent=1;try{if(cm)cm.setValue(sheet());else if(ta)ta.value=sheet()}finally{window.__upSilent=0}head()}
 function flip(dir){const ds=dates();if(!ds.includes(S.cur))ds.push(S.cur),ds.sort();const i=ds.indexOf(S.cur)+dir;if(i>=0&&i<ds.length)load(ds[i]);else if(dir>0)load(today())}

 /* ---- синхронизация листов с сервером (/api/notes, id=pad-YYYY-MM-DD); localStorage = офлайн-кэш ---- */
 let pt=0,pulling=0;
 function push(){clearTimeout(pt);pt=setTimeout(doPush,1500)}
 async function doPush(){try{const j=await jget('/api/notes');if(!j)return;let list=(j.notes||[]).slice();
   Object.keys(S.sheets).forEach(function(d){const t=S.sheets[d];if(!t||!t.trim())return;const id='pad-'+d;const rec={id:id,text:t,ts:S.ts[d]||Date.now()/1000,proj:S.proj[d]||'',pad:1};const i=list.findIndex(function(n){return n.id===id});if(i>=0){if((list[i].ts||0)>rec.ts+1)return;list[i]=rec}else list.push(rec)});
   const r=await fetch('/api/notes',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({notes:list})});if(r.ok)flash('синхронизировано')}catch(e){}}
 async function pull(){if(pulling)return;pulling=1;try{const j=await jget('/api/notes');if(!j)return;let ch=0;(j.notes||[]).forEach(function(n){if(!n||!/^pad-\d{4}-\d\d-\d\d$/.test(n.id))return;const d=n.id.slice(4);if((n.ts||0)>(S.ts[d]||0)+1){S.sheets[d]=n.text||'';S.ts[d]=n.ts;if(n.proj)S.proj[d]=n.proj;ch=1}});
   if(ch){save();window.__upSilent=1;try{if(cm&&cm.getValue()!==sheet())cm.setValue(sheet());else if(!cm&&ta)ta.value=sheet();head()}finally{window.__upSilent=0}}}finally{pulling=0}}
 /* ---- действия ---- */
 async function jget(u){try{const r=await fetch(u,{cache:'no-store'});return r.ok?await r.json():null}catch(e){return null}}
 async function toNox(text){text=String(text||'').trim();if(!text)return false;let ok=false;
  const j=await jget('/api/notes');const list=(j&&j.notes)||[];list.push({id:String(Date.now()),text:text.slice(0,4000),ts:Date.now()/1000});
  try{const r=await fetch('/api/notes',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({notes:list})});ok=r.ok}catch(e){}
  try{const r=await fetch('/svc/nox-living/mem/add',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:'Заметка владельца: '+text.slice(0,1500)})});ok=ok||r.ok}catch(e){}
  return ok}
 function toBoard(text){text=String(text||'').trim();if(!text)return false;try{const d=JSON.parse(localStorage.getItem(BK)||'{}');const els=d.elements||[];let y=40;els.forEach(function(e){if(e&&typeof e.y==='number')y=Math.max(y,e.y+(e.height||0)+20)});
   const id=Math.random().toString(36).slice(2,12),tid=Math.random().toString(36).slice(2,12),w=240,h=Math.max(110,Math.ceil(text.length/22)*24+30),base={angle:0,strokeWidth:1,strokeStyle:'solid',roughness:1,opacity:100,groupIds:[],frameId:null,seed:Math.floor(Math.random()*1e9),version:1,versionNonce:Math.floor(Math.random()*1e9),isDeleted:false,updated:Date.now(),link:null,locked:false};
   els.push(Object.assign({},base,{id:id,type:'rectangle',x:40,y:y,width:w,height:h,strokeColor:'#9aa3b2',backgroundColor:'#d9dde3',fillStyle:'solid',roundness:{type:3},boundElements:[{type:'text',id:tid}]}));
   els.push(Object.assign({},base,{id:tid,type:'text',x:50,y:y+12,width:w-20,height:h-24,strokeColor:'#1f2124',backgroundColor:'transparent',fillStyle:'solid',roundness:null,boundElements:null,text:text,fontSize:18,fontFamily:1,textAlign:'left',verticalAlign:'top',containerId:id,originalText:text,lineHeight:1.25}));
   localStorage.setItem(BK,JSON.stringify(Object.assign({},d,{elements:els})));if(/board/.test(location.pathname))setTimeout(function(){location.reload()},600);return true}catch(e){return false}}
 function append(text){text=String(text||'').trim();if(!text)return;const cur=(cm?cm.getValue():sheet()).replace(/\s+$/,'');const nv=(cur?cur+'\n':'')+text+'\n';S.sheets[today()]=(S.cur===today()?nv:(S.sheets[today()]||'')+(S.sheets[today()]?'\n':'')+text+'\n');if(S.cur!==today())S.cur=today();S.ts[S.cur]=Date.now()/1000;save();push();if(cm){cm.setValue(sheet());cm.setCursor(cm.lineCount(),0)}else if(ta)ta.value=sheet();if(root)head()}
 async function add(text,o){o=o||{};const to=o.to||'pad';if(to==='pad'||to==='both')append(text);let r=true;if(to==='nox'||to==='both')r=(await toNox(text))&&r;if(to==='board'||to==='both')r=toBoard(text)&&r;flash(r?'Записано':'Не удалось записать');return r}
 function selText(){let t=cm?cm.getSelection():'';if(!t&&cm){t=cm.getLine(cm.getCursor().line)}return(t||'').trim()}
 function flash(m){const s=root&&root.querySelector('.st');if(!s)return;s.textContent=m;clearTimeout(flash.t);flash.t=setTimeout(function(){s.textContent=saved?'сохранено':''},2200)}
 /* ---- голос ---- */
 function mic(){const R=window.SpeechRecognition||window.webkitSpeechRecognition;if(!R){flash('Голос не поддерживается');return}if(rec){try{rec.stop()}catch(e){}return}rec=new R();rec.lang='ru-RU';rec.interimResults=false;rec.onresult=function(e){const t=e.results[0][0].transcript;if(cm)cm.replaceSelection(t+' ');else ta.value+=t+' ';flash('Вставлено голосом')};rec.onend=rec.onerror=function(){rec=null;root.querySelector('[data-a=mic]').style.background=''};root.querySelector('[data-a=mic]').style.background='color-mix(in srgb,var(--ds-bad,#d66) 40%,transparent)';try{rec.start()}catch(e){rec=null}}
 /* ---- поиск по листам ---- */
 function search(q){q=String(q||'').toLowerCase().trim();const out=[];if(!q)return out;Object.keys(S.sheets).sort().reverse().forEach(function(d){String(S.sheets[d]).split('\n').forEach(function(l,i){if(l.toLowerCase().includes(q))out.push({d:d,l:l.trim().slice(0,90),i:i})})});return out.slice(0,30)}
 function showSearch(q){const box=root.querySelector('.up-s');const r=search(q);if(!q){box.hidden=true;return}box.hidden=false;box.innerHTML=r.length?r.map(function(x,i){return '<button type="button" data-d="'+x.d+'" data-i="'+x.i+'"><b>'+x.d+'</b>&nbsp;'+esc(x.l)+'</button>'}).join(''):'<div style="padding:8px;opacity:.7">Ничего не найдено</div>'}
 /* ---- UI ---- */
 function build(){const st=document.createElement('style');st.textContent=CSS;document.head.appendChild(st);
  root=document.createElement('aside');root.id='u-pad';root.setAttribute('aria-label','Блокнот');root.className=S.open?'open':'shut';root.style.setProperty('--w',S.w+'px');
  root.innerHTML='<div id="u-grip" title="Ширина"></div><div class="up-h"><button type="button" data-a="prev" aria-label="Предыдущий лист" title="Предыдущий лист">‹</button><b></b><button type="button" data-a="next" aria-label="Следующий лист" title="Следующий лист">›</button><button type="button" data-a="min" aria-label="Свернуть блокнот" title="Свернуть (N)">»</button></div>'+
   '<div class="up-p"><span>Проект</span><input type="text" placeholder="общий" aria-label="Проект листа"><input type="search" class="up-q" placeholder="Поиск по листам" aria-label="Поиск по листам" style="flex:1.2"></div><div class="up-s" hidden></div>'+
   '<div class="up-ed"><textarea class="up-raw" aria-label="Лист блокнота" placeholder="Пиши сюда. Каждая строка — запись."></textarea></div>'+
   '<div class="up-f"><button type="button" class="up-go" data-a="nox" title="Выделенное или текущая строка в память NOX">→ NOX</button><button type="button" class="up-go" data-a="board" title="Стикер на доску">→ Доска</button><button type="button" data-a="mic" aria-label="Голосовой ввод" title="Голос">Голос</button><button type="button" data-a="new" title="Новый лист (сегодня)">+ Лист</button><span class="st"></span></div>';
  document.body.appendChild(root);
  tab=document.createElement('button');tab.id='u-tab';tab.type='button';tab.textContent='Блокнот';tab.setAttribute('aria-label','Открыть блокнот');document.body.appendChild(tab);if(S.open){document.body.classList.add('u-pad-open');document.documentElement.style.setProperty('--u-pad-w',S.w+'px')}
  ta=root.querySelector('.up-raw');ta.value=sheet();head();
  const onchg=function(){if(window.__upSilent)return;setSheet(cm?cm.getValue():ta.value);saved=1;flash('сохранено')};
  ta.addEventListener('input',onchg);
  /* CodeMirror 5 из vendor */
  const l=document.createElement('link');l.rel='stylesheet';l.href='./vendor/codemirror/codemirror.css';document.head.appendChild(l);
  const sc=document.createElement('script');sc.src='./vendor/codemirror/codemirror.iife.js';sc.onload=function(){try{const g=window.NOX_codemirror;const C=g&&(g.fromTextArea?g:(g.default||g));if(!C||!C.fromTextArea)return;cm=C.fromTextArea(ta,{lineWrapping:true,lineNumbers:false,viewportMargin:Infinity});cm.setValue(sheet());cm.on('change',onchg);root.querySelector('.up-ed').classList.add('cm');if(S.open)setTimeout(function(){cm.refresh()},300)}catch(e){}};document.head.appendChild(sc);
  root.addEventListener('click',function(e){const b=e.target.closest('button');if(!b)return;const a=b.dataset.a;
   if(b.dataset.d){load(b.dataset.d);root.querySelector('.up-s').hidden=true;root.querySelector('.up-q').value='';setTimeout(function(){if(cm){cm.setCursor(+b.dataset.i,0);cm.focus()}},50);return}
   if(a==='prev')flip(-1);else if(a==='next')flip(1);else if(a==='min')close();
   else if(a==='nox')toNox(selText()).then(function(ok){flash(ok?'→ NOX: записано':'Не удалось')});
   else if(a==='board')flash(toBoard(selText())?'→ Доска: стикер':'Не удалось');
   else if(a==='mic')mic();else if(a==='new'){load(today())}});
  root.querySelector('.up-p input').addEventListener('input',function(e){S.proj[S.cur]=e.target.value;S.ts[S.cur]=Date.now()/1000;save();push()});
  root.querySelector('.up-q').addEventListener('input',function(e){showSearch(e.target.value)});
  tab.addEventListener('click',open);
  /* ширина */
  const g=root.querySelector('#u-grip');g.addEventListener('pointerdown',function(e){e.preventDefault();g.setPointerCapture(e.pointerId);const mv=function(ev){S.w=Math.max(240,Math.min(560,innerWidth-ev.clientX));root.style.setProperty('--w',S.w+'px');if(cm)cm.refresh()};const up=function(){g.removeEventListener('pointermove',mv);g.removeEventListener('pointerup',up);save()};g.addEventListener('pointermove',mv);g.addEventListener('pointerup',up)});
  /* хоткей */
  document.addEventListener('keydown',function(e){const t=e.target;const typing=t&&(/INPUT|TEXTAREA|SELECT/.test(t.tagName)||t.isContentEditable||(t.closest&&t.closest('.CodeMirror')));
   if(((e.key==='n'||e.key==='N'||e.key==='т'||e.key==='Т')&&!e.ctrlKey&&!e.altKey&&!e.metaKey&&!typing)||((e.metaKey||e.ctrlKey)&&e.shiftKey&&(e.key==='n'||e.key==='N'))){e.preventDefault();open(true)}
   else if(e.key==='Escape'&&root.classList.contains('open')&&typing&&t.closest&&t.closest('#u-pad')){if(cm)cm.getInputField().blur();else ta.blur()}});
  /* свайп от правого края (мобильный) */
  let sx=null;document.addEventListener('touchstart',function(e){const t=e.touches[0];sx=(innerWidth-t.clientX<24)?t.clientX:null},{passive:true});
  document.addEventListener('touchend',function(e){if(sx==null)return;const t=e.changedTouches[0];if(sx-t.clientX>50)open();sx=null},{passive:true});
  /* «→ NOX / → Доска» на выделенном тексте страницы */
  let pop;document.addEventListener('mouseup',function(e){if(e.target.closest&&e.target.closest('#u-pad,#u-pop'))return;setTimeout(function(){const s=String(getSelection()||'').trim();if(pop){pop.remove();pop=null}if(s.length<3||s.length>1500)return;const r=getSelection().getRangeAt(0).getBoundingClientRect();pop=document.createElement('div');pop.id='u-pop';pop.style.cssText='position:fixed;z-index:8100;left:'+Math.max(8,Math.min(innerWidth-250,r.left))+'px;top:'+Math.max(8,r.top-52)+'px;display:flex;gap:4px;padding:4px;border-radius:12px;border:1px solid var(--ds-line,rgba(255,255,255,.2));background:var(--ds-glass,rgba(30,32,36,.95));backdrop-filter:blur(12px)';
    pop.innerHTML='<button type="button" data-t="pad">В блокнот</button><button type="button" data-t="nox">→ NOX</button><button type="button" data-t="board">→ Доска</button>';pop.querySelectorAll('button').forEach(function(b){b.style.cssText='min-height:44px;padding:0 10px;border-radius:10px;border:1px solid var(--ds-line,rgba(255,255,255,.2));background:transparent;color:var(--ds-ink,#e6e7ea);font:inherit;font-size:14px;cursor:pointer';b.addEventListener('click',function(){add(s,{to:b.dataset.t});pop.remove();pop=null})});document.body.appendChild(pop)},10)});
  document.addEventListener('mousedown',function(e){if(pop&&!(e.target.closest&&e.target.closest('#u-pop'))){pop.remove();pop=null}});
 }
 function open(focus){document.body.classList.add('u-pad-open');root.style.setProperty('--w',S.w+'px');document.documentElement.style.setProperty('--u-pad-w',S.w+'px');root.classList.remove('shut');root.classList.add('open');S.open=true;save();setTimeout(function(){if(cm){cm.refresh();if(focus===true)cm.focus()}else if(focus===true)ta.focus()},280)}
 function close(){document.body.classList.remove('u-pad-open');root.classList.add('shut');root.classList.remove('open');S.open=false;save()}
 function init(){build();pull();setInterval(function(){if(!document.hidden)pull()},60000);document.addEventListener('visibilitychange',function(){if(!document.hidden)pull()})}
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
 window.NOXNote={add:add,open:function(){open(true)},close:close,toggle:function(){root.classList.contains('open')?close():open(true)},search:search,sheets:function(){return Object.assign({},S.sheets)}};
})();
