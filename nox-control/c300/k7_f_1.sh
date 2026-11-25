echo "C300: k7_f_1"
S=/workspace/nox/web/site; cd $S; TS=$(date +%s)
cat > nox-k7-ui.css <<'K7EOF'
.k7-row{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:8px 0}
.k7-in{min-height:44px;padding:0 12px;border-radius:12px;border:1px solid rgba(255,255,255,.22);background:rgba(255,255,255,.06);color:#efe6df;font-size:14px;box-sizing:border-box}
.k7-st{font-size:12px;opacity:.75;margin:6px 0}
.k7-snap{display:flex;gap:12px;overflow-x:auto;scroll-snap-type:x mandatory;padding:4px 2px 10px}
.k7-card{flex:0 0 min(320px,82%);scroll-snap-align:start;border:1px solid rgba(255,255,255,.18);border-radius:14px;padding:12px;background:rgba(255,255,255,.05);display:flex;flex-direction:column;gap:8px}
.k7-card h4{margin:0;font-size:15px;line-height:1.3}
.k7-card p{margin:0;font-size:13px;opacity:.85}
.k7-hit{display:flex;align-items:center;gap:8px;min-height:44px;padding:4px 10px;border-radius:10px;color:#efe6df;text-decoration:none;font-size:14px;border:1px solid transparent;background:transparent;width:100%;text-align:left;cursor:pointer}
.k7-hit:hover,.k7-hit:focus-visible,.k7-hit.on{background:rgba(233,180,101,.25);border-color:rgba(233,180,101,.6);outline:0}
.k7-hit small{font-size:12px;opacity:.65;margin-left:auto}
#k7-mesh{position:fixed;inset:0;z-index:0;pointer-events:none;opacity:.45;mix-blend-mode:screen;transition:opacity .4s}
#k7-wall{position:fixed;inset:0;z-index:9000;background:#07050a;display:flex;flex-direction:column}
#k7-wall iframe{flex:1;border:0;width:100%}
#k7-wall .k7-wb{display:flex;gap:10px;align-items:center;padding:6px 12px;font-size:14px;color:#efe6df}
#k7-wall .k7-wp{height:3px;background:#e9b465;width:0}
#k7-attr-p{position:fixed;right:12px;bottom:96px;z-index:46;width:min(300px,calc(100vw - 24px));padding:12px;border-radius:14px;background:rgba(20,15,15,.92);border:1px solid rgba(255,255,255,.22);color:#efe6df;backdrop-filter:blur(12px);font-size:14px}
#k7-attr-p sl-range{--thumb-size:22px;margin:6px 0;min-height:44px}
#k7-attr-p label{font-size:12px;opacity:.8;display:block}
K7EOF
cat > nox-k7-cards.js <<'K7EOF'
/* K7 №14: карточки-обновления (расширить, глубже, сохранить). API K7cards.open() */
(function(){ if(window.K7cards||!window.K4)return; let d;
 const SK='nox.k7.saved';const saved=function(){try{return JSON.parse(localStorage.getItem(SK)||'[]')}catch(e){return[]}};
 async function open(){ const a=(await K4.news()).slice(0,8);
  if(!d){d=K4.modal('k7-cards-d','Карточки обновлений')}
  d.innerHTML='<div class="k7-snap" id="k7-cs"></div><div class="k7-st" id="k7-cst">Свайп вбок; «Глубже» просит NOX разобрать тему.</div>';
  const box=d.querySelector('#k7-cs');
  if(!a.length)box.innerHTML='<div class="k7-st">Обновлений пока нет</div>';
  a.forEach(function(x,i){const c=document.createElement('div');c.className='k7-card';
   c.innerHTML='<small class="k7-st">'+K4.esc(x.src||'')+' · '+K4.esc(x.cat||'')+'</small><h4>'+K4.esc(x.title)+'</h4><p class="k7-sm" hidden>'+K4.esc(x.sum||'Без описания')+'</p><div class="k7-row"><button type="button" class="k4-btn k7-ex" aria-expanded="false">Расширить</button><button type="button" class="k4-btn k7-dp">Глубже</button><button type="button" class="k4-btn k7-sv" aria-pressed="false">Сохранить</button></div><div class="k7-ao k7-st"></div>';
   const sm=c.querySelector('.k7-sm'),ex=c.querySelector('.k7-ex'),sv=c.querySelector('.k7-sv');
   ex.addEventListener('click',function(){sm.hidden=!sm.hidden;ex.setAttribute('aria-expanded',String(!sm.hidden));ex.textContent=sm.hidden?'Расширить':'Свернуть'});
   c.querySelector('.k7-dp').addEventListener('click',function(){const o=c.querySelector('.k7-ao');o.textContent='NOX думает…';K4.ask('Разбери глубже, 3-4 предложения по-русски, что важно знать: '+x.title+'. '+(x.sum||''),o)});
   const on=function(){return saved().some(function(s){return s.url===x.url})};sv.setAttribute('aria-pressed',String(on()));sv.textContent=on()?'Сохранено':'Сохранить';
   sv.addEventListener('click',function(){let s=saved();if(on())s=s.filter(function(q){return q.url!==x.url});else s.push({title:x.title,url:x.url,src:x.src});localStorage.setItem(SK,JSON.stringify(s));sv.setAttribute('aria-pressed',String(on()));sv.textContent=on()?'Сохранено':'Сохранить'});
   box.appendChild(c)});
  d.show();return a.length}
 K4.fab('k7-cards','Обновления','cards',function(){open()});window.K7cards={open:open,saved:saved};
})();
K7EOF
cat > nox-k7-find.js <<'K7EOF'
/* K7 №15: универсальный поиск (страницы, задачи, новости, сохранённое). Alt+F. API K7find.search(q), K7find.open() */
(function(){ if(window.K7find||!window.K4)return; let d,idx=null;
 async function build(){ const r=[];
  document.querySelectorAll('#tbSheet a[href],#nxnavx a[href],nav a[href]').forEach(function(a){const t=(a.textContent||'').trim();if(t&&/\.html|^\.\//.test(a.getAttribute('href')))r.push({k:'Страница',t:t.slice(0,60),u:a.getAttribute('href')})});
  K4.tasks().forEach(function(t){r.push({k:'Задача',t:t.title,u:'./projects.html'})});
  (await K4.news()).forEach(function(n){r.push({k:'Новость',t:n.title,u:n.url,x:n.src})});
  try{JSON.parse(localStorage.getItem('nox.k7.saved')||'[]').forEach(function(n){r.push({k:'Сохранено',t:n.title,u:n.url})})}catch(e){}
  const seen={};idx=r.filter(function(x){const k=x.k+x.t;if(seen[k])return false;return seen[k]=1});return idx}
 async function search(q){ if(!idx)await build();const w=q.toLowerCase().split(/\s+/).filter(Boolean);if(!w.length)return idx.slice(0,10);
  return idx.map(function(x){const s=(x.t+' '+(x.x||'')+' '+x.k).toLowerCase();let sc=0;for(const k of w){if(s.indexOf(k)<0){sc=-1;break}sc+=s.indexOf(k)===0?3:1}return{x:x,sc:sc}}).filter(function(h){return h.sc>0}).sort(function(a,b){return b.sc-a.sc}).slice(0,12).map(function(h){return h.x})}
 function show(h){const o=d.querySelector('#k7-fo');o.innerHTML=h.length?'':'<div class="k7-st">Ничего не найдено</div>';h.forEach(function(x){const a=document.createElement('a');a.className='k7-hit';a.href=x.u;if(/^https?:/.test(x.u)){a.target='_blank';a.rel='noopener'}a.innerHTML='<span>'+K4.esc(x.t.slice(0,90))+'</span><small>'+K4.esc(x.k)+'</small>';o.appendChild(a)})}
 async function open(){ if(!d){d=K4.modal('k7-find-d','Найти везде');d.innerHTML='<input id="k7-fq" class="k7-in" style="width:100%" aria-label="Поиск" placeholder="Страница, задача, новость…" autocomplete="off"><div id="k7-fo"></div>';
   const q=d.querySelector('#k7-fq');q.addEventListener('input',async function(){show(await search(q.value))});
   q.addEventListener('keydown',function(e){if(e.key==='Enter'){const a=d.querySelector('.k7-hit');if(a)a.click()}})}
  idx=null;d.show();show(await search(''));setTimeout(function(){const q=d.querySelector('#k7-fq');q&&q.focus()},200)}
 document.addEventListener('keydown',function(e){if(e.altKey&&(e.key==='f'||e.key==='F'||e.key==='а'||e.key==='А')){e.preventDefault();open()}});
 K4.fab('k7-find','Найти везде','search',function(){open()});window.K7find={open:open,search:search};
})();
K7EOF
cat > nox-k7-mesh.js <<'K7EOF'
/* K7 №37: градиентная сетка-фон, мягко следует за курсором. API K7mesh.on/off */
(function(){ if(window.K7mesh)return; const el=document.createElement('div');el.id='k7-mesh';(document.getElementById('app')||document.body).prepend(el);
 let x=.5,y=.4,tx=.5,ty=.4,raf=0;const red=matchMedia('(prefers-reduced-motion: reduce)').matches;
 function draw(){x+=(tx-x)*.06;y+=(ty-y)*.06;el.style.background='radial-gradient(520px circle at '+(x*100)+'% '+(y*100)+'%,rgba(233,180,101,.35),transparent 60%),radial-gradient(640px circle at '+((1-x)*100)+'% '+((1-y)*100)+'%,rgba(120,90,200,.28),transparent 62%),radial-gradient(420px circle at '+(50+(x-.5)*60)+'% '+(30+(y-.5)*40)+'%,rgba(60,160,190,.2),transparent 65%)';
  if(Math.abs(tx-x)+Math.abs(ty-y)>.002)raf=requestAnimationFrame(draw);else raf=0}
 function kick(){if(!raf)raf=requestAnimationFrame(draw)}
 if(!red)addEventListener('pointermove',function(e){tx=e.clientX/innerWidth;ty=e.clientY/innerHeight;kick()},{passive:true});
 draw();window.K7mesh={on:function(){el.style.display=''},off:function(){el.style.display='none'},el:el};
})();
K7EOF
cat > nox-k7-wall.js <<'K7EOF'
/* K7 №18: режим стены, авторотация экранов. API K7wall.start(sec), K7wall.stop() */
(function(){ if(window.K7wall||!window.K4||window.top!==window)return; let w,t,lock,i=0;
 const P=['system.html','finance.html','news.html','index.html'];
 function show(){ const f=w.querySelector('iframe');f.src='./'+P[i%P.length]+'?wall=1';w.querySelector('#k7-wn').textContent=P[i%P.length].replace('.html','');i++;
  const b=w.querySelector('.k7-wp');b.style.transition='none';b.style.width='0';requestAnimationFrame(function(){requestAnimationFrame(function(){b.style.transition='width '+w._s+'s linear';b.style.width='100%'})})}
 function start(s){ stop();s=s||15;w=document.createElement('div');w.id='k7-wall';w._s=s;w.innerHTML='<div class="k7-wp"></div><div class="k7-wb"><span id="k7-wn"></span><button type="button" class="k4-btn" id="k7-wx">Выйти</button></div><iframe title="Экран стены"></iframe>';
  document.body.appendChild(w);w.querySelector('#k7-wx').addEventListener('click',stop);i=0;show();t=setInterval(show,s*1000);
  try{navigator.wakeLock&&navigator.wakeLock.request('screen').then(function(l){lock=l}).catch(function(){})}catch(e){}}
 function stop(){ clearInterval(t);if(w){w.remove();w=null}try{lock&&lock.release()}catch(e){}lock=null}
 addEventListener('keydown',function(e){if(e.key==='Escape'&&w)stop()});
 K4.fab('k7-wall-b','Режим стены','device-tv',function(){start(15)});window.K7wall={start:start,stop:stop,active:function(){return!!w}};
})();
K7EOF
cat > nox-k7-attr.js <<'K7EOF'
/* K7 №17: слайдеры атрибутов изображения (яркость, контраст, насыщенность, тепло, размытие) + «теплее на 20%». API K7attr.set(имя,знач), K7attr.apply(текст), K7attr.get() */
(function(){ if(window.K7attr||!window.K4)return; let p;
 const D={bright:100,contrast:100,sat:100,warm:0,blur:0};const V=Object.assign({},D);
 const L={bright:['Яркость',50,150],contrast:['Контраст',50,150],sat:['Насыщенность',0,200],warm:['Тепло',-50,50],blur:['Размытие',0,10]};
 const W={bright:/ярч|светлее|темнее|яркост/,contrast:/контраст/,sat:/насыщ|сочн|ярк\w* цвет/,warm:/тепл|холодн|холоднее/,blur:/размы|мягч/};
 function css(){return'brightness('+V.bright+'%) contrast('+V.contrast+'%) saturate('+V.sat+'%) sepia('+Math.max(0,V.warm)*1.2+'%) hue-rotate('+(V.warm<0?V.warm*2.4:V.warm*-.4)+'deg) blur('+V.blur+'px)'}
 function apply_(){const f=css();document.querySelectorAll('.FIE_root canvas,#gTh img,#fie canvas').forEach(function(e){e.style.filter=f})}
 function set(k,v){if(!(k in V))return;V[k]=+v;apply_();if(p){const r=p.querySelector('sl-range[data-k="'+k+'"]');if(r&&+r.value!==+v)r.value=+v}}
 function apply(txt){const s=String(txt).toLowerCase();const m=s.match(/(\d+)\s*%/);const n=m?+m[1]:15;const neg=/холодн|темнее|мягч|меньше|слабее/.test(s);let hit=0;
  for(const k in W){if(W[k].test(s)){hit=1;let sg=neg?-1:1;if(k==='warm'&&/холодн/.test(s))sg=-1;else if(k==='warm')sg=1;if(k==='blur')sg=1;const base=k==='warm'||k==='blur'?V[k]:V[k];set(k,Math.max(L[k][1],Math.min(L[k][2],base+sg*(k==='blur'?n/10:k==='warm'?n/2:n))))}}return hit}
 function open(){ if(!p){p=document.createElement('div');p.id='k7-attr-p';let h='<b>Атрибуты фото</b>';
   for(const k in L)h+='<label>'+L[k][0]+'<sl-range data-k="'+k+'" min="'+L[k][1]+'" max="'+L[k][2]+'" value="'+V[k]+'" step="1"></sl-range></label>';
   h+='<div class="k7-row"><input id="k7-ai" class="k7-in" style="flex:1;min-width:120px" aria-label="Команда" placeholder="теплее на 20%"><button type="button" class="k4-btn" id="k7-ag">ОК</button><button type="button" class="k4-btn" id="k7-ar">Сброс</button></div><div class="k7-st" id="k7-as"></div>';p.innerHTML=h;document.body.appendChild(p);
   p.querySelectorAll('sl-range').forEach(function(r){r.addEventListener('sl-input',function(){set(r.dataset.k,r.value)})});
   const go=function(){const q=p.querySelector('#k7-ai');p.querySelector('#k7-as').textContent=apply(q.value)?'Применено':'Не понял команду';q.value=''};
   p.querySelector('#k7-ag').addEventListener('click',go);p.querySelector('#k7-ai').addEventListener('keydown',function(e){if(e.key==='Enter')go()});
   p.querySelector('#k7-ar').addEventListener('click',function(){for(const k in D)set(k,D[k])})}
  else p.hidden=!p.hidden}
 K4.fab('k7-attr-b','Атрибуты фото','adjustments',open);window.K7attr={set:set,apply:apply,get:function(){return Object.assign({},V)},css:css,open:open};
 new MutationObserver(apply_).observe(document.body,{childList:true,subtree:true});
})();
K7EOF
add(){ f=$1.html; [ -f $f ] || { echo "no $f"; return; }
 grep -q "nox-k7-$2.js" $f && { echo "have $f $2"; return; }
 cp $f $f.bak_k7_$TS; tag=""
 grep -q "nox-k4-core.js" $f || tag="<script src=\"./nox-k4-core.js?v=k4a\" defer></script>"
 grep -q "nox-k7-ui.css" $f || tag="$tag<link rel=\"stylesheet\" href=\"./nox-k7-ui.css?v=k7a\">"
 tag="$tag<script src=\"./nox-k7-$2.js?v=k7a\" defer></script>"
 python3 - "$f" "$tag" <<'PYX'
import sys
f,t=sys.argv[1],sys.argv[2]
s=open(f,encoding='utf-8').read();i=s.rfind('</body>')
open(f,'w',encoding='utf-8').write(s[:i]+t+s[i:] if i>=0 else s+t)
PYX
 echo "added $2 -> $f"; }
add index cards; add index find; add index mesh; add system wall; add photo attr
echo "K7: №14 карточки-обновления (cards)" >> qa/rework/index.fixed
echo "K7: №15 универсальный поиск Alt+F (find)" >> qa/rework/index.fixed
echo "K7: №37 градиентная сетка за курсором (mesh)" >> qa/rework/index.fixed
echo "K7: №18 режим стены (wall)" >> qa/rework/system.fixed
echo "K7: №17 слайдеры атрибутов фото (attr)" >> qa/rework/photo.fixed
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python
timeout 220 $PY - <<'QAEOF'
import asyncio
from playwright.async_api import async_playwright
T={'index':("K7cards",None),'system':("K7wall",None),'photo':("K7attr",None)}
JS={
'index':"""(async()=>{const o={};await K7cards.open();await new Promise(r=>setTimeout(r,800));const c=document.querySelectorAll('#k7-cs .k7-card');o.cards=c.length;if(c.length){c[0].querySelector('.k7-ex').click();o.exp=!c[0].querySelector('.k7-sm').hidden;c[0].querySelector('.k7-sv').click();o.sv=K7cards.saved().length}
const f=await K7find.search('новост');o.find=f.length;const g=await K7find.search('');o.all=g.length;o.mesh=!!document.getElementById('k7-mesh');
const bt=[...document.querySelectorAll('#k4-fab button,#k7-cs button')].map(x=>x.getBoundingClientRect().height).filter(x=>x>0);o.minbtn=bt.length?Math.min(...bt):-1;return JSON.stringify(o)})()""",
'system':"""(async()=>{K7wall.start(5);await new Promise(r=>setTimeout(r,1200));const o={act:K7wall.active(),src:document.querySelector('#k7-wall iframe').src.split('/').pop()};K7wall.stop();o.after=K7wall.active();return JSON.stringify(o)})()""",
'photo':"""(async()=>{K7attr.open();K7attr.apply('теплее на 20%');K7attr.apply('контрастнее на 10%');const o=K7attr.get();K7attr.apply('ярче на 15%');o.b=K7attr.get().bright;const r=document.querySelectorAll('#k7-attr-p sl-range').length;o.ranges=r;const bt=[...document.querySelectorAll('#k7-attr-p button')].map(x=>x.getBoundingClientRect().height);o.minbtn=Math.min(...bt);return JSON.stringify(o)})()"""}
async def m():
  async with async_playwright() as p:
    b=await p.chromium.launch(args=[])
    for w,h in((1440,900),(390,844)):
      for pg_ in ('index','system','photo'):
        pg=await b.new_page(viewport={'width':w,'height':h});errs=[];pg.on('pageerror',lambda e:errs.append(str(e)[:140]))
        try:
          await pg.goto('http://127.0.0.1:8091/web/%s.html'%pg_,wait_until='domcontentloaded',timeout=40000);await pg.wait_for_function('window.%s'%T[pg_][0],timeout=15000);await pg.wait_for_timeout(1500)
          r=await asyncio.wait_for(pg.evaluate(JS[pg_]),40);print('QA',w,pg_,r,'errs',errs[:3])
        except Exception as e: print('QA EXC',w,pg_,str(e)[:300],errs[:3])
        await pg.close()
    await b.close()
asyncio.run(m())
QAEOF
echo "K7: пакет 1 (№14,15,37,18,17) внедрён. Файлы site/nox-k7-<имя>.js, общий nox-k7-ui.css; бэкапы *.bak_k7_<ts>." >> /workspace/nox/web/site/K7_LOG.md 2>/dev/null
echo "K7 f1 done"
