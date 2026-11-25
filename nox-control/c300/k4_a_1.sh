echo "C300: k4_a_1"
S=/workspace/nox/web/site; cd $S
TS=$(date +%s)
cat > nox-k4-core.js <<'K4EOF'
/* K4 core: общие помощники. K4.load, K4.css, K4.esc, K4.ask (через K3.ask -> /api/chat), K4.modal (sl-dialog), K4.fab, K4.tasks, K4.glob */
(function(){ if(window.K4)return;
 const loaded={};
 const K={
  esc:function(s){return String(s==null?'':s).replace(/[&<>"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})},
  load:function(src){ if(loaded[src])return loaded[src]; return loaded[src]=new Promise(function(ok){const s=document.createElement('script');s.src=src;s.onload=ok;s.onerror=function(){ok()};document.head.appendChild(s)})},
  ask:function(prompt,el){ return K.load('./nox-k3-core.js').then(function(){return window.K3?K3.ask(prompt,el):(el.textContent='NOX недоступен')})},
  glob:function(g){ if(!g)return null; return g.default&&(typeof g.default==='function'||typeof g.default==='object')?g.default:g},
  tasks:function(){try{const j=JSON.parse(localStorage.getItem('nox.tasks.v1')||'{}');return(j.tasks||[]).filter(function(t){return t&&t.id&&t.title})}catch(e){return[]}},
  saveTasks:function(a){localStorage.setItem('nox.tasks.v1',JSON.stringify({v:2,tasks:a}))},
  ymd:function(d){const p=function(n){return String(n).padStart(2,'0')};return d.getFullYear()+'-'+p(d.getMonth()+1)+'-'+p(d.getDate())},
  news:function(){return fetch('./data/news.json',{cache:'no-store'}).then(function(r){return r.ok?r.json():{items:[]}}).then(function(j){return j.items||[]}).catch(function(){return[]})},
  modal:function(id,label){ let d=document.getElementById(id); if(d)return d;
   d=document.createElement('sl-dialog');d.id=id;d.label=label;d.className='k4-dlg';document.body.appendChild(d);return d},
  fab:function(id,label,icon,fn){ let box=document.getElementById('k4-fab');
   if(!box){box=document.createElement('div');box.id='k4-fab';document.body.appendChild(box)}
   if(document.getElementById(id))return;
   const b=document.createElement('button');b.type='button';b.id=id;b.className='k4-fab-b';b.setAttribute('aria-label',label);
   b.innerHTML=(icon?'<sl-icon library="tabler" name="'+icon+'"></sl-icon>':'')+'<span>'+K.esc(label)+'</span>';
   b.addEventListener('click',fn);box.appendChild(b);return b},
  ready:function(fn){ if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',fn);else fn()},
  wait:function(sel,fn,n){let i=0;const t=setInterval(function(){const e=document.querySelector(sel);if(e){clearInterval(t);fn(e)}else if(++i>(n||80))clearInterval(t)},250)}
 };
 window.K4=K;
 if(!document.getElementById('k4-core-css')){const l=document.createElement('link');l.id='k4-core-css';l.rel='stylesheet';l.href='./nox-k4-core.css?v=k4a';document.head.appendChild(l)}
})();
K4EOF
cat > nox-k4-core.css <<'K4EOF'
#k4-fab{position:fixed;left:12px;bottom:96px;z-index:45;display:flex;flex-direction:column;gap:8px}
.k4-fab-b{display:inline-flex;align-items:center;gap:6px;min-width:44px;min-height:44px;padding:0 14px;border-radius:22px;border:1px solid rgba(255,255,255,.22);background:rgba(20,15,15,.82);color:#efe6df;font-size:14px;cursor:pointer;backdrop-filter:blur(10px)}
.k4-fab-b:hover,.k4-fab-b:focus-visible{background:rgba(233,180,101,.3);outline:0}
.k4-fab-b sl-icon{font-size:18px}
.k4-dlg::part(panel){background:rgba(24,18,18,.95);backdrop-filter:blur(18px);color:#efe6df}
.k4-dlg::part(title){font-size:16px}
.k4-btn{min-width:44px;min-height:44px;padding:0 16px;border-radius:12px;border:1px solid rgba(255,255,255,.22);background:rgba(255,255,255,.08);color:#efe6df;font-size:14px;cursor:pointer}
.k4-btn:hover,.k4-btn:focus-visible{background:rgba(233,180,101,.3);outline:0}
.k4-btn.pri{background:rgba(233,180,101,.35);border-color:rgba(233,180,101,.7)}
.k4-btn[aria-pressed=true]{background:rgba(233,180,101,.4);border-color:#e9b465}
.k4-in{min-height:44px;box-sizing:border-box;padding:0 12px;border-radius:12px;border:1px solid rgba(255,255,255,.22);background:rgba(0,0,0,.35);color:#efe6df;font-size:14px;font-family:inherit}
.k4-box{margin:0 0 16px;padding:14px;border-radius:18px;background:rgba(20,15,15,.92);border:1px solid rgba(255,255,255,.12);color:#efe6df}
.k4-box h3{margin:0 0 8px;font-size:16px;font-weight:400}
.k4-out{white-space:pre-wrap;font-size:14px;margin-top:12px;color:#efe6df}
.k4-muted{font-size:12px;color:#a89c93}
@media(max-width:600px){#k4-fab{bottom:84px}.k4-fab-b span{display:none}}
K4EOF
cat > nox-k4-wx.js <<'K4EOF'
/* K4 №6 (atlas): живые карточки погоды и циклонов (Open-Meteo: ветер, давление). Команда «покажи ветер» в поле окна. Узлы NOX кликаются как на глобусе. */
(function(){
 const P=[['S1 · Квебек',46.81,-71.21,'s1'],['S2 · США',39.8,-98.6,'s2'],['Москва',55.75,37.62],['Лондон',51.5,-0.12],['Токио',35.68,139.69],['Сидней',-33.87,151.21]];
 let wind=true,data=null,d;
 const dir=function(a){return['С','СВ','В','ЮВ','Ю','ЮЗ','З','СЗ'][Math.round(a/45)%8]};
 function card(p,c){ if(!c)return '<div class="k4-wc"><b>'+K4.esc(p[0])+'</b><span class="k4-muted">нет данных</span></div>';
  const cy=c.surface_pressure<1000||c.wind_speed_10m>=55;
  return '<div class="k4-wc'+(cy?' cy':'')+'" data-id="'+(p[3]||'')+'" tabindex="0" role="button"><b>'+K4.esc(p[0])+'</b><span class="k4-t">'+Math.round(c.temperature_2m)+'°</span>'+
   (wind?'<span class="k4-w"><i style="transform:rotate('+Math.round(c.wind_direction_10m+180)+'deg)">↑</i> '+Math.round(c.wind_speed_10m)+' км/ч '+dir(c.wind_direction_10m)+'</span>':'')+
   '<span class="k4-p">'+Math.round(c.surface_pressure)+' гПа</span>'+(cy?'<em>циклон / шторм</em>':'')+'</div>'}
 function paint(){ const g=d.querySelector('#k4-wg');g.innerHTML=P.map(function(p,i){return card(p,data&&data[i])}).join('')}
 async function fetchAll(){ const o=d.querySelector('#k4-wn');o.textContent='Загрузка…';
  try{const u='https://api.open-meteo.com/v1/forecast?latitude='+P.map(function(p){return p[1]}).join(',')+'&longitude='+P.map(function(p){return p[2]}).join(',')+'&current=temperature_2m,wind_speed_10m,wind_direction_10m,surface_pressure';
   const r=await fetch(u);if(!r.ok)throw new Error('HTTP '+r.status);const j=await r.json();const a=Array.isArray(j)?j:[j];data=a.map(function(x){return x.current});
   const n=data.filter(function(c){return c&&(c.surface_pressure<1000||c.wind_speed_10m>=55)}).length;o.textContent='Обновлено '+new Date().toTimeString().slice(0,5)+(n?' · очагов: '+n:' · очагов нет')}
  catch(e){data=null;o.textContent='Погода недоступна: нужен выход браузера в интернет ('+e.message+')'}
  paint()}
 function cmd(t){t=t.toLowerCase();if(/ветер/.test(t)){wind=!/скрой|убери|выключи/.test(t);paint();return 'Ветер: '+(wind?'показан':'скрыт')}
  if(/обнов|погод/.test(t)){fetchAll();return 'Обновляю'} return 'Команды: «покажи ветер», «скрой ветер», «обнови»'}
 function open(){ if(!d){d=K4.modal('k4-wx-d','Погода и циклоны');
   d.innerHTML='<div id="k4-wg"></div><p class="k4-muted" id="k4-wn"></p><form id="k4-wf"><input class="k4-in" id="k4-wq" aria-label="Команда" placeholder="покажи ветер" value="покажи ветер"><button class="k4-btn pri" type="submit">Выполнить</button><button class="k4-btn" type="button" id="k4-wr">Обновить</button></form>';
   d.querySelector('#k4-wf').addEventListener('submit',function(e){e.preventDefault();d.querySelector('#k4-wn').textContent=cmd(d.querySelector('#k4-wq').value)});
   d.querySelector('#k4-wr').addEventListener('click',fetchAll);
   d.querySelector('#k4-wg').addEventListener('click',function(e){const c=e.target.closest('.k4-wc[data-id]');if(!c||!c.dataset.id)return;const n=document.querySelector('.at-node[data-id="'+c.dataset.id+'"]');if(n){d.hide();n.click()}});
   fetchAll()} d.show()}
 K4.ready(function(){K4.fab('k4-wx-b','Ветер и циклоны','wind',open)});
})();
K4EOF
cat > nox-k4-wx.css <<'K4EOF'
#k4-wg{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px}
.k4-wc{min-height:44px;padding:10px;border-radius:14px;background:rgba(255,255,255,.07);border:1px solid rgba(255,255,255,.12);display:flex;flex-direction:column;gap:2px;font-size:14px;cursor:pointer}
.k4-wc[data-id=""]{cursor:default}
.k4-wc b{font-weight:400}.k4-wc .k4-t{font-size:24px}
.k4-wc .k4-w,.k4-wc .k4-p{font-size:12px;color:#cbbfb6}
.k4-wc .k4-w i{display:inline-block;font-style:normal;color:#e9b465}
.k4-wc.cy{border-color:#ff7a6e;background:rgba(255,90,80,.15)}
.k4-wc em{font-size:12px;font-style:normal;color:#ff9a8e}
#k4-wf{display:flex;flex-wrap:wrap;gap:8px;margin-top:8px}#k4-wf .k4-in{flex:1;min-width:140px}
K4EOF
cat > nox-k4-fly.js <<'K4EOF'
/* K4 №7 (atlas): «облети X»: облёт города по команде (поле поиска атласа или окно). MapLibre из vendor, геокодер Nominatim как в атласе. */
(function(){
 let d,map,raf=0,t0=0,go=false;
 const V='/web/vendor/nox-x/maplibre/';
 function stop(){go=false;cancelAnimationFrame(raf)}
 function spin(ts){ if(!go)return; if(!t0)t0=ts; const k=(ts-t0)/1000; map.setBearing((k*14)%360); map.setPitch(55+8*Math.sin(k/2)); map.setZoom(map.getZoom()); raf=requestAnimationFrame(spin);
  if(k>40)stop()}
 async function ensure(){ if(map)return; if(!window.maplibregl){const l=document.createElement('link');l.rel='stylesheet';l.href=V+'maplibre-gl.css';document.head.appendChild(l);await K4.load(V+'maplibre-gl.js')}
  map=new maplibregl.Map({container:d.querySelector('#k4-fm'),center:[37.62,55.75],zoom:14,pitch:55,attributionControl:{compact:true},
   style:{version:8,sources:{osm:{type:'raster',tiles:['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],tileSize:256,attribution:'© OpenStreetMap'}},layers:[{id:'bg',type:'background',paint:{'background-color':'#0a0608'}},{id:'osm',type:'raster',source:'osm',paint:{'raster-brightness-max':.7,'raster-saturation':-.3}}]}});
  map.on('error',function(){d.querySelector('#k4-fn').textContent='Тайлы недоступны: нужен выход браузера в интернет.'})}
 async function fly(q){ const n=d.querySelector('#k4-fn');q=q.replace(/^\s*(облети|облёт|облететь)\s+/i,'').trim();if(!q){n.textContent='Назовите город: «облети Париж»';return}
  n.textContent='Ищу «'+q+'»…';
  try{const r=await fetch('https://nominatim.openstreetmap.org/search?format=json&limit=1&q='+encodeURIComponent(q));const j=await r.json();if(!j.length){n.textContent='Ничего не найдено.';return}
   await ensure();stop();t0=0;n.textContent='Облёт: '+j[0].display_name.slice(0,90);
   map.jumpTo({center:[+j[0].lon,+j[0].lat],zoom:14,pitch:58,bearing:0});go=true;raf=requestAnimationFrame(spin)}
  catch(e){n.textContent='Поиск недоступен: '+e.message}}
 function open(q){ if(!d){d=K4.modal('k4-fly-d','Облёт города');
   d.innerHTML='<form id="k4-ff"><input class="k4-in" id="k4-fq" aria-label="Команда облёта" placeholder="облети Париж"><button class="k4-btn pri" type="submit">Лететь</button><button class="k4-btn" type="button" id="k4-fs">Стоп</button></form><p class="k4-muted" id="k4-fn">Введите «облети» и название города.</p><div id="k4-fm"></div>';
   d.querySelector('#k4-ff').addEventListener('submit',function(e){e.preventDefault();fly(d.querySelector('#k4-fq').value)});
   d.querySelector('#k4-fs').addEventListener('click',stop);
   d.addEventListener('sl-after-show',function(){if(map)map.resize()});d.addEventListener('sl-after-hide',function(e){if(e.target===d)stop()})}
  d.show(); if(q){d.querySelector('#k4-fq').value=q;setTimeout(function(){fly(q)},250)}}
 K4.ready(function(){K4.fab('k4-fly-b','Облёт города','plane',function(){open()});
  const f=document.getElementById('atSearch');
  if(f)f.addEventListener('submit',function(e){const q=(document.getElementById('atQ').value||'').trim();if(/^(облети|облёт|облететь)\s+/i.test(q)){e.preventDefault();e.stopImmediatePropagation();open(q)}},true)});
})();
K4EOF
cat > nox-k4-fly.css <<'K4EOF'
#k4-fm{width:100%;height:min(52vh,420px);border-radius:14px;overflow:hidden;margin-top:8px}
#k4-ff{display:flex;flex-wrap:wrap;gap:8px}#k4-ff .k4-in{flex:1;min-width:140px}
K4EOF
cat > nox-k4-nl.js <<'K4EOF'
/* K4 №8 (calendar): строка быстрого события в духе Fantastical: «встреча завтра в 15:00»; слова даты и времени подсвечиваются цветом при вводе (chrono-node). */
(function(){
 function go(){ const w=document.querySelector('#page .wrap'),g=w&&w.querySelector('.grid');if(!g||document.getElementById('k4-nl'))return;
  const b=document.createElement('section');b.id='k4-nl';b.className='k4-box';
  b.innerHTML='<h3>Быстрое событие</h3><form id="k4-nf"><input class="k4-in" id="k4-ni" aria-label="Событие словами" placeholder="встреча завтра в 15:00 с Аней" autocomplete="off"><button class="k4-btn pri" type="submit">Добавить</button></form><div id="k4-np" class="k4-np" aria-live="polite"></div>';
  w.insertBefore(b,g);
  const ch=function(){const C=window.NOX_chrono_node;return C?(C.ru||(C.default&&C.default.ru)||C.default||C):null};
  function parse(t){const C=ch();if(!C||!t.trim())return null;let r;try{r=(C.ru||C).parse(t,new Date(),{forwardDate:true})}catch(e){return null}
   if(!r||!r.length)return {rs:[],date:null};
   const f=r[0],dt=f.start.date(),timed=f.start.isCertain('hour');return {rs:r,date:dt,timed:timed}}
  function view(){const t=b.querySelector('#k4-ni').value,o=b.querySelector('#k4-np'),p=parse(t);
   if(!t.trim()){o.innerHTML='<span class="k4-muted">Дата, время и название подсветятся цветом</span>';return}
   if(!p){o.innerHTML='<span class="k4-muted">Разбор недоступен</span>';return}
   let h='',pos=0;p.rs.forEach(function(r){h+='<span class="k4-tt">'+K4.esc(t.slice(pos,r.index))+'</span><mark class="k4-dm">'+K4.esc(r.text)+'</mark>';pos=r.index+r.text.length});
   h+='<span class="k4-tt">'+K4.esc(t.slice(pos))+'</span>';
   if(p.date)h+='<div class="k4-muted">→ '+p.date.toLocaleDateString('ru-RU',{weekday:'short',day:'numeric',month:'long'})+(p.timed?' · '+p.date.toTimeString().slice(0,5):' · весь день')+'</div>';
   else h+='<div class="k4-muted">Дата не найдена: событие встанет на сегодня</div>';o.innerHTML=h}
  b.querySelector('#k4-ni').addEventListener('input',view);view();
  b.querySelector('#k4-nf').addEventListener('submit',function(e){e.preventDefault();const t=b.querySelector('#k4-ni').value.trim();if(!t)return;const p=parse(t)||{rs:[]};
   let title=t;p.rs.forEach(function(r){title=title.replace(r.text,' ')});title=title.replace(/\b(в|на|к|во)\s*$/i,'').replace(/\s+/g,' ').trim()||t;
   const dt=p.date||new Date(),a=K4.tasks(),p2=function(n){return String(n).padStart(2,'0')};
   a.push({id:'t'+Date.now().toString(36)+Math.random().toString(36).slice(2,6),kind:'event',col:'queue',title:title,due:K4.ymd(dt),time:p.timed?p2(dt.getHours())+':'+p2(dt.getMinutes()):'',note:'',project:'',owner:'',created:Date.now()});
   K4.saveTasks(a);b.querySelector('#k4-np').innerHTML='<span class="k4-ok">Добавлено: '+K4.esc(title)+' · '+K4.ymd(dt)+'</span>';b.querySelector('#k4-ni').value='';
   setTimeout(function(){location.reload()},900)})}
 K4.ready(function(){K4.load('./vendor/chrono-node/chrono-node.iife.js').then(function(){go()})});
})();
K4EOF
cat > nox-k4-nl.css <<'K4EOF'
#k4-nf{display:flex;flex-wrap:wrap;gap:8px}#k4-nf .k4-in{flex:1;min-width:200px}
.k4-np{min-height:44px;margin-top:8px;font-size:14px}
.k4-np .k4-dm{background:rgba(233,180,101,.3);color:#ffd9a0;border-radius:6px;padding:2px 4px}
.k4-np .k4-tt{color:#8fe3b0}
.k4-np .k4-ok{color:#8fe3b0}
K4EOF
cat > nox-k4-inbox.js <<'K4EOF'
/* K4 №12 (index): приоритетный входящий: два потока «Сейчас» и «Подождёт», перетаскивание (sortablejs), «Что срочно» -> /api/chat. Источник: задачи 'nox.tasks.v1'. */
(function(){
 const KEY='nox.k4.inbox';
 function ov(){try{return JSON.parse(localStorage.getItem(KEY)||'{}')}catch(e){return{}}}
 function go(S){ const w=document.querySelector('#page .wrap'),g=document.getElementById('svc');if(!w||document.getElementById('k4-ib'))return;
  const b=document.createElement('section');b.id='k4-ib';b.className='k4-box';
  b.innerHTML='<h3>Входящие: что срочно</h3><div class="k4-ibg"><div><div class="k4-ibh">Сейчас</div><ul class="k4-ibl" data-s="now"></ul></div><div><div class="k4-ibh">Подождёт</div><ul class="k4-ibl" data-s="later"></ul></div></div><button class="k4-btn pri" type="button" id="k4-ibq">Что срочно?</button><div class="k4-out" id="k4-ibo"></div>';
  w.insertBefore(b,g||w.children[2]||null);
  const tasks=K4.tasks().filter(function(t){return t.col!=='done'}),o=ov(),lim=K4.ymd(new Date(Date.now()+2*864e5));
  tasks.sort(function(a,c){return(a.due||'9').localeCompare(c.due||'9')});
  const L={now:b.querySelector('[data-s=now]'),later:b.querySelector('[data-s=later]')};
  tasks.slice(0,40).forEach(function(t){const s=o[t.id]||((t.due&&t.due<=lim)?'now':'later'),li=document.createElement('li');li.dataset.id=t.id;
   li.innerHTML='<b>'+K4.esc(t.title)+'</b><small>'+(t.due?K4.esc(t.due.slice(8)+'.'+t.due.slice(5,7))+(t.time?' '+K4.esc(t.time):''):'без срока')+'</small>';L[s].appendChild(li)});
  Object.keys(L).forEach(function(k){if(!L[k].children.length){L[k].dataset.empty='1'}});
  const save=function(){const m={};['now','later'].forEach(function(k){L[k].querySelectorAll('li').forEach(function(li){m[li.dataset.id]=k})});localStorage.setItem(KEY,JSON.stringify(m))};
  const Sx=K4.glob(S);
  if(Sx&&Sx.create)['now','later'].forEach(function(k){Sx.create(L[k],{group:'k4ib',animation:150,delay:120,delayOnTouchOnly:true,onEnd:save})});
  b.querySelector('#k4-ibq').addEventListener('click',function(){const n=[].map.call(L.now.querySelectorAll('li b'),function(x){return x.textContent});
   K4.ask(n.length?'Вот мои срочные дела: '+n.join('; ')+'. Расставь по порядку, что делать первым. Коротко.':'У меня нет срочных дел. Скажи одной фразой, что стоит запланировать.',b.querySelector('#k4-ibo'))})}
 K4.ready(function(){K4.load('./vendor/sortablejs/sortablejs.iife.js').then(function(){go(window.NOX_sortablejs)})});
})();
K4EOF
cat > nox-k4-inbox.css <<'K4EOF'
.k4-ibg{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px}
@media(max-width:600px){.k4-ibg{grid-template-columns:1fr}}
.k4-ibh{font-size:14px;color:#e9b465;margin-bottom:6px}
.k4-ibl{list-style:none;margin:0;padding:6px;min-height:56px;border-radius:12px;background:rgba(255,255,255,.05);border:1px dashed rgba(255,255,255,.18)}
.k4-ibl:empty::after{content:'пусто: перетащите сюда';font-size:12px;color:#a89c93}
.k4-ibl li{min-height:44px;box-sizing:border-box;display:flex;justify-content:space-between;align-items:center;gap:8px;padding:8px 10px;margin:4px 0;border-radius:10px;background:rgba(255,255,255,.09);font-size:14px;cursor:grab}
.k4-ibl li b{font-weight:400}.k4-ibl li small{font-size:12px;color:#a89c93;white-space:nowrap}
K4EOF
cat > nox-k4-curate.js <<'K4EOF'
/* K4 №13 (news): «Curate for tomorrow»: выбор тем завтрашней сводки (профиль в localStorage), сводка через /api/chat по заголовкам ленты. */
(function(){
 const KEY='nox.k4.topics',T=['Россия','Мир','Экономика','Технологии','Наука','Спорт','Культура','Общество'];
 function go(){ const r=document.getElementById('nwRoot');if(!r||document.getElementById('k4-cu'))return;
  let sel;try{sel=JSON.parse(localStorage.getItem(KEY)||'[]')}catch(e){sel=[]}
  const b=document.createElement('section');b.id='k4-cu';b.className='k4-box';
  b.innerHTML='<h3>Сводка на завтра: выберите темы</h3><div class="k4-chips" role="group" aria-label="Темы"></div><button class="k4-btn pri" type="button" id="k4-cug">Собрать сводку</button><div class="k4-out" id="k4-cuo"></div>';
  r.parentNode.insertBefore(b,r);
  const ch=b.querySelector('.k4-chips');
  T.forEach(function(t){const x=document.createElement('button');x.type='button';x.className='k4-btn';x.textContent=t;x.setAttribute('aria-pressed',sel.indexOf(t)>=0);
   x.addEventListener('click',function(){const i=sel.indexOf(t);if(i>=0)sel.splice(i,1);else sel.push(t);x.setAttribute('aria-pressed',i<0);localStorage.setItem(KEY,JSON.stringify(sel))});ch.appendChild(x)});
  b.querySelector('#k4-cug').addEventListener('click',async function(){const o=b.querySelector('#k4-cuo');
   if(!sel.length){o.textContent='Отметьте хотя бы одну тему.';return}
   const it=await K4.news();const h=it.slice(0,30).map(function(i){return '- '+i.title}).join('\n');
   K4.ask('Составь сводку на завтра по темам: '+sel.join(', ')+'. Выбери из заголовков самые важные и коротко (до 6 пунктов) объясни, почему они важны.\n'+(h||'(лента пуста, сформулируй общий план чтения)'),o)})}
 K4.ready(go);
})();
K4EOF
cat > nox-k4-curate.css <<'K4EOF'
.k4-chips{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:12px}
K4EOF
add(){ f=$1.html; [ -f $f ] || { echo "no $f"; return; }
 grep -q "nox-k4-$2.js" $f && { echo "have $f $2"; return; }
 cp $f $f.bak_k4_$TS; tag=""
 grep -q "nox-k4-core.js" $f || tag="<script src=\"./nox-k4-core.js?v=k4a\" defer></script>"
 [ -f nox-k4-$2.css ] && tag="$tag<link rel=\"stylesheet\" href=\"./nox-k4-$2.css?v=k4a\">"
 [ -f nox-k4-$2.js ] && tag="$tag<script src=\"./nox-k4-$2.js?v=k4a\" defer></script>"
 python3 - "$f" "$tag" <<'PY'
import sys
f,t=sys.argv[1],sys.argv[2]
s=open(f,encoding='utf-8').read();i=s.rfind('</body>')
open(f,'w',encoding='utf-8').write(s[:i]+t+s[i:] if i>=0 else s+t)
PY
 echo "added $2 -> $f"; }
add atlas wx
echo "K4: №6 карточки погоды и циклонов (wx)" >> qa/rework/atlas.fixed
add atlas fly
echo "K4: №7 облёт города (fly)" >> qa/rework/atlas.fixed
add calendar nl
echo "K4: №8 быстрое событие словами (nl)" >> qa/rework/calendar.fixed
add index inbox
echo "K4: №12 приоритетный входящий (inbox)" >> qa/rework/index.fixed
add news curate
echo "K4: №13 сводка на завтра (curate)" >> qa/rework/news.fixed
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python
timeout 250 $PY /tmp/k2_qa.py atlas calendar index news 2>&1 | tail -14
$PY - <<'PY'
import asyncio
from playwright.async_api import async_playwright
C=[["atlas", "(async()=>{const a=document.getElementById('k4-wx-b'),f=document.getElementById('k4-fly-b');if(!a||!f)return 'NO FAB';a.click();await new Promise(r=>setTimeout(r,4000));const d=document.getElementById('k4-wx-d');return JSON.stringify({fab:[a.offsetHeight,f.offsetHeight],open:d&&d.open,cards:document.querySelectorAll('.k4-wc').length,note:(document.getElementById('k4-wn')||{}).textContent})})()"], ["calendar", "(async()=>{const i=document.getElementById('k4-ni');if(!i)return 'NO';i.value='встреча завтра в 15:00 с Аней';i.dispatchEvent(new Event('input'));await new Promise(r=>setTimeout(r,300));return JSON.stringify({mark:document.querySelectorAll('.k4-dm').length,txt:document.getElementById('k4-np').innerText.slice(0,120)})})()"], ["index", "(async()=>{const b=document.getElementById('k4-ib');if(!b)return 'NO';return JSON.stringify({now:b.querySelectorAll('[data-s=now] li').length,later:b.querySelectorAll('[data-s=later] li').length,sortable:!!window.NOX_sortablejs})})()"], ["news", "(async()=>{const b=document.getElementById('k4-cu');if(!b)return 'NO';const c=b.querySelectorAll('.k4-chips button');c[0].click();return JSON.stringify({chips:c.length,pressed:c[0].getAttribute('aria-pressed'),h:c[0].offsetHeight})})()"]]
async def m():
  async with async_playwright() as p:
    b=await p.chromium.launch(args=['--use-gl=swiftshader','--enable-unsafe-swiftshader'])
    for w,h in((1440,900),(390,844)):
      for u,js in C:
        pg=await b.new_page(viewport={'width':w,'height':h});errs=[];pg.on('pageerror',lambda e:errs.append(str(e)[:120]))
        try:
          await pg.goto('http://127.0.0.1:8091/web/'+u+'.html',wait_until='load',timeout=25000);await pg.wait_for_timeout(3500)
          r=await pg.evaluate(js)
        except Exception as e: r='EXC '+str(e)[:160]
        print(w,u,r,'errs',len(errs),errs[:2])
        await pg.close()
    await b.close()
asyncio.run(m())
PY

