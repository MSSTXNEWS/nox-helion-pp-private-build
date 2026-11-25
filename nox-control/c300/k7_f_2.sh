echo "C300: k7_f_2"
S=/workspace/nox/web/site; cd $S; TS=$(date +%s)
cat >> nox-k7-ui.css <<'K7EOF'
.k7-chip{display:inline-flex;align-items:center;gap:6px;min-height:44px;padding:0 10px;margin:2px 6px 2px 0;border-radius:22px;border:1px solid rgba(255,255,255,.22);background:rgba(255,255,255,.07);color:#efe6df;font-size:12px;text-decoration:none;cursor:pointer}
.k7-chip:hover,.k7-chip:focus-visible{background:rgba(233,180,101,.28);outline:0}
.k7-chip i{display:inline-grid;place-items:center;width:20px;height:20px;border-radius:50%;font-style:normal;font-size:12px;color:#14100e;background:var(--k7c,#e9b465)}
#k7-rel{display:flex;flex-wrap:wrap;gap:6px;padding:4px 0}
#k7-rel .k7-chip{font-size:13px}
#k7-sel{position:absolute;z-index:9100;display:none}
#k7-sel.on{display:block}
#k7-pres{display:flex;flex-wrap:wrap;align-items:center;gap:10px;margin:10px 0;padding:10px 14px;border-radius:14px;border:1px solid rgba(255,255,255,.18);background:rgba(255,255,255,.05);font-size:14px;color:#efe6df}
#k7-pres .dot{width:10px;height:10px;border-radius:50%;background:#7fd48a;box-shadow:0 0 8px #7fd48a;animation:k7p 2s infinite}
@keyframes k7p{50%{opacity:.35}}
@media (prefers-reduced-motion:reduce){#k7-pres .dot{animation:none}}
K7EOF
cat > nox-k7-cover.js <<'K7EOF'
/* K7 №21: цветной акцент страницы по обложке трека. API K7cover.apply(), K7cover.color() */
(function(){ if(window.K7cover)return; let col='';const st=document.createElement('style');st.id='k7-cover-css';document.head.appendChild(st);
 function hash(s){let h=0;for(let i=0;i<s.length;i++)h=(h*31+s.charCodeAt(i))|0;return'hsl('+(Math.abs(h)%360)+',60%,52%)'}
 function paint(c){col=c;document.documentElement.style.setProperty('--k7-acc',c);st.textContent='#page{background:linear-gradient(180deg,color-mix(in srgb,'+c+' 22%,transparent),transparent 420px)!important;transition:background .8s}.mu-pb,.mu-pr{accent-color:'+c+'}'}
 function avg(src){return new Promise(function(ok){const im=new Image();im.crossOrigin='anonymous';im.onload=function(){try{const c=document.createElement('canvas');c.width=c.height=8;const x=c.getContext('2d');x.drawImage(im,0,0,8,8);const d=x.getImageData(0,0,8,8).data;let r=0,g=0,b=0,n=0;for(let i=0;i<d.length;i+=4){r+=d[i];g+=d[i+1];b+=d[i+2];n++}ok('rgb('+(r/n|0)+','+(g/n|0)+','+(b/n|0)+')')}catch(e){ok('')}};im.onerror=function(){ok('')};im.src=src})}
 async function apply(){ const cv=document.getElementById('bCv');const t=(document.getElementById('bT')||{}).textContent||'';let src='';
  if(cv){const im=cv.querySelector('img');if(im)src=im.currentSrc||im.src;else{const m=(getComputedStyle(cv).backgroundImage||'').match(/url\(["']?(.*?)["']?\)/);if(m)src=m[1]}}
  let c=src?await avg(src):'';if(!c)c=hash(t||'nox');paint(c);return c}
 let tm;const mo=new MutationObserver(function(){clearTimeout(tm);tm=setTimeout(apply,300)});
 const go=function(){const e=document.getElementById('bCv')||document.getElementById('muB');if(e){mo.observe(document.getElementById('muB')||e,{subtree:true,childList:true,attributes:true,characterData:true});apply()}else setTimeout(go,800)};
 if(window.K4)K4.ready(go);else go();window.K7cover={apply:apply,color:function(){return col}};
})();
K7EOF
cat > nox-k7-chips.js <<'K7EOF'
/* K7 №27: чипы источников с номерами на карточках новостей. API K7chips.run() */
(function(){ if(window.K7chips||!window.K4)return; let items=[],busy=0;
 function hue(s){let h=0;for(let i=0;i<s.length;i++)h=(h*31+s.charCodeAt(i))|0;return'hsl('+(Math.abs(h)%360)+',55%,62%)'}
 function run(){ if(busy||!items.length)return 0;busy=1;let n=0;
  document.querySelectorAll('.nw-lead,.nw-li,.nw-cd').forEach(function(el){ if(el.dataset.k7)return;const tx=(el.textContent||'').replace(/\s+/g,' ');
   const i=items.findIndex(function(x){return x.title&&tx.indexOf(x.title.slice(0,32))>=0});if(i<0)return;el.dataset.k7='1';const x=items[i];
   const a=document.createElement('a');a.className='k7-chip';a.href=x.url;a.target='_blank';a.rel='noopener';a.style.setProperty('--k7c',hue(x.src||''));a.setAttribute('aria-label','Источник '+(i+1)+': '+(x.src||''));
   a.innerHTML='<i>'+K4.esc((x.src||'?').trim().charAt(0).toUpperCase())+'</i>['+(i+1)+'] '+K4.esc((x.src||'').slice(0,28));
   const row=document.createElement('div');row.className='k7-chiprow';row.appendChild(a);el.appendChild(row);n++});
  busy=0;return n}
 K4.news().then(function(a){items=a;run();let t;new MutationObserver(function(){clearTimeout(t);t=setTimeout(run,400)}).observe(document.getElementById('nwRoot')||document.body,{childList:true,subtree:true})});
 window.K7chips={run:run,count:function(){return document.querySelectorAll('.k7-chip').length}};
})();
K7EOF
cat > nox-k7-related.js <<'K7EOF'
/* K7 №28: три чипа «спроси дальше» под ответом. API K7rel.make(текст), K7rel.chips() */
(function(){ if(window.K7rel||!window.K4)return; let row,tm,last='',sent='';
 const FB=['Объясни подробнее','Приведи пример','Скажи то же короче'];
 function box(){ if(row)return row;const f=document.getElementById('form');if(!f)return null;row=document.createElement('div');row.id='k7-rel';row.setAttribute('role','group');row.setAttribute('aria-label','Продолжить вопросом');f.parentNode.insertBefore(row,f);return row}
 function put(q){const r=box();if(!r)return;r.innerHTML='';q.slice(0,3).forEach(function(t){const b=document.createElement('button');b.type='button';b.className='k7-chip';b.textContent=t;b.addEventListener('click',function(){const i=document.getElementById('input');i.value=t;i.dispatchEvent(new Event('input',{bubbles:true}));const s=document.getElementById('btnSend');s&&s.click();r.innerHTML=''});r.appendChild(b)})}
 async function make(txt){ const el=document.createElement('div');const p='Ответ ассистента:\n'+String(txt).slice(0,900)+'\n\nПридумай 3 коротких (до 7 слов) вопроса, которые пользователь мог бы задать дальше. По одному на строку, без нумерации.';
  try{await Promise.race([K4.ask(p,el),new Promise(function(r){setTimeout(r,25000)})])}catch(e){}
  const t=el.textContent||'';let q=t.split(/\n+/).map(function(s){return s.replace(/^[\-\d\.\)\s•*]+/,'').trim()}).filter(function(s){return s.length>3&&s.length<70&&/\?$|^[А-ЯЁA-Z]/.test(s)});
  if(/занят|недоступ/i.test(t)||q.length<2)q=FB;return q.slice(0,3)}
 function check(){ const m=document.getElementById('msgs');if(!m||!m.lastElementChild)return;const tx=(m.lastElementChild.textContent||'').trim();
  if(tx.length<40||tx===last||(sent&&tx.indexOf(sent)===0&&tx.length<sent.length+5))return;if(document.getElementById('btnStop')&&getComputedStyle(document.getElementById('btnStop')).display!=='none'&&document.getElementById('btnStop').offsetParent)return;
  last=tx;make(tx).then(put)}
 function arm(){const m=document.getElementById('msgs');if(!m){setTimeout(arm,800);return}new MutationObserver(function(){if(row)row.innerHTML='';clearTimeout(tm);tm=setTimeout(check,2500)}).observe(m,{childList:true,subtree:true,characterData:true});
  const i=document.getElementById('input');if(i)i.addEventListener('keydown',function(e){if(e.key==='Enter')sent=i.value.trim()});const s=document.getElementById('btnSend');if(s)s.addEventListener('click',function(){sent=(i&&i.value||'').trim()},true)}
 K4.ready(arm);window.K7rel={make:make,put:put,chips:function(){return row?row.querySelectorAll('.k7-chip').length:0}};
})();
K7EOF
cat > nox-k7-seldoc.js <<'K7EOF'
/* K7 №36: подсказка «спроси документ» по выделению текста. API K7sel.ask(текст) */
(function(){ if(window.K7sel||!window.K4)return; const b=document.createElement('div');b.id='k7-sel';b.innerHTML='<button type="button" class="k4-btn pri">Спросить NOX</button>';document.body.appendChild(b);let cur='',d;
 function ask(t){ if(!d){d=K4.modal('k7-sel-d','Объяснить выделенное')}d.innerHTML='<blockquote class="k7-st" id="k7-sq" style="font-size:13px;margin:0 0 8px"></blockquote><div class="k7-row"><button type="button" class="k4-btn pri" data-m="explain">Объясни</button><button type="button" class="k4-btn" data-m="short">Кратко</button><button type="button" class="k4-btn" data-m="tr">Перевод</button></div><div id="k7-sa" style="font-size:14px;white-space:pre-wrap"></div>';
  d.querySelector('#k7-sq').textContent=t.slice(0,400);const o=d.querySelector('#k7-sa');
  const P={explain:'Объясни простыми словами этот фрагмент документа: ',short:'Перескажи кратко, одним предложением: ',tr:'Переведи на русский (если уже русский — на английский): '};
  const run=function(m){o.textContent='NOX думает…';K4.ask(P[m]+t.slice(0,1500),o)};
  d.querySelectorAll('[data-m]').forEach(function(x){x.addEventListener('click',function(){run(x.dataset.m)})});d.show();run('explain')}
 function upd(){ const s=getSelection();const t=s?String(s).trim():'';
  if(t.length<12||!s.rangeCount||(s.anchorNode&&s.anchorNode.parentElement&&s.anchorNode.parentElement.closest('input,textarea,sl-dialog,#k7-sel,nav,header'))){b.classList.remove('on');return}
  cur=t;const r=s.getRangeAt(0).getBoundingClientRect();b.style.top=(scrollY+Math.max(8,r.top-52))+'px';b.style.left=Math.max(8,Math.min(innerWidth-170,scrollX+r.left))+'px';b.classList.add('on')}
 document.addEventListener('mouseup',function(){setTimeout(upd,50)});document.addEventListener('touchend',function(){setTimeout(upd,300)});document.addEventListener('keyup',function(e){if(e.shiftKey)upd()});
 b.addEventListener('mousedown',function(e){e.preventDefault()});b.querySelector('button').addEventListener('click',function(){b.classList.remove('on');ask(cur)});
 window.K7sel={ask:ask,show:function(t){cur=t;b.style.top=scrollY+80+'px';b.style.left='20px';b.classList.add('on')}};
})();
K7EOF
cat > nox-k7-presence.js <<'K7EOF'
/* K7 №34: статус-присутствие NOX «чем занят сейчас». API K7pres.state(), K7pres.ask() */
(function(){ if(window.K7pres||!window.K4)return; let box,o;
 function state(){ const g=(document.getElementById('gwStatus')||{}).textContent||'';const f=(document.getElementById('tFast')||{}).textContent||'';const d=(document.getElementById('tDeep')||{}).textContent||'';
  const h=new Date().getHours();const part=h<6?'ночью':h<12?'утром':h<18?'днём':'вечером';
  return{gw:g.trim(),fast:f.trim(),deep:d.trim(),line:(g.trim()||'на связи')+(f.trim()?' · быстрый: '+f.trim():'')+(d.trim()?' · глубокий: '+d.trim():'')+' · '+part}}
 function draw(){ box.querySelector('#k7-pl').textContent=state().line}
 function ask(){ const s=state();o.textContent='NOX думает…';K4.ask('Ты NOX. Одной-двумя фразами от первого лица скажи, чем ты сейчас занят. Состояние шлюза: '+s.line+'.',o)}
 function mount(){ const pg=document.getElementById('page');if(!pg)return;box=document.createElement('section');box.id='k7-pres';box.setAttribute('aria-label','Присутствие NOX');
  box.innerHTML='<span class="dot" aria-hidden="true"></span><b>NOX сейчас:</b><span id="k7-pl"></span><button type="button" class="k4-btn" id="k7-pa">Чем занят?</button><div id="k7-po" style="flex-basis:100%;font-size:14px"></div>';
  pg.insertBefore(box,pg.firstChild);o=box.querySelector('#k7-po');box.querySelector('#k7-pa').addEventListener('click',ask);draw();setInterval(draw,8000)}
 K4.ready(mount);window.K7pres={state:state,ask:ask};
})();
K7EOF
add(){ f=$1.html; [ -f $f ] || { echo "no $f"; return; }
 grep -q "nox-k7-$2.js" $f && { echo "have $f $2"; return; }
 cp $f $f.bak_k7_$TS; tag=""
 grep -q "nox-k4-core.js" $f || tag="<script src=\"./nox-k4-core.js?v=k4a\" defer></script>"
 grep -q "nox-k7-ui.css" $f || tag="$tag<link rel=\"stylesheet\" href=\"./nox-k7-ui.css?v=k7b\">"
 tag="$tag<script src=\"./nox-k7-$2.js?v=k7a\" defer></script>"
 python3 - "$f" "$tag" <<'PYX'
import sys
f,t=sys.argv[1],sys.argv[2]
s=open(f,encoding='utf-8').read();i=s.rfind('</body>')
open(f,'w',encoding='utf-8').write(s[:i]+t+s[i:] if i>=0 else s+t)
PYX
 echo "added $2 -> $f"; }
# новая версия css для страниц пакета 1
for p in index system photo; do sed -i 's/nox-k7-ui.css?v=k7a/nox-k7-ui.css?v=k7b/' $p.html; done
add music cover; add news chips; add chat related; add pdf seldoc; add soul presence
echo "K7: №21 акцент по обложке (cover)" >> qa/rework/music.fixed
echo "K7: №27 чипы источников (chips)" >> qa/rework/news.fixed
echo "K7: №28 related-вопросы (related)" >> qa/rework/chat.fixed
echo "K7: №36 спроси документ по выделению (seldoc)" >> qa/rework/pdf.fixed
echo "K7: №34 присутствие NOX (presence)" >> qa/rework/soul.fixed
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python
timeout 220 $PY - <<'QAEOF'
import asyncio
from playwright.async_api import async_playwright
T={'music':"K7cover",'news':"K7chips",'chat':"K7rel",'pdf':"K7sel",'soul':"K7pres"}
JS={
'music':"""(async()=>{const c=await K7cover.apply();return JSON.stringify({c:c,v:getComputedStyle(document.documentElement).getPropertyValue('--k7-acc')})})()""",
'news':"""(async()=>{await new Promise(r=>setTimeout(r,2500));K7chips.run();const ch=[...document.querySelectorAll('.k7-chip')];return JSON.stringify({n:K7chips.count(),minh:ch.length?Math.min(...ch.map(x=>x.getBoundingClientRect().height)):-1})})()""",
'chat':"""(async()=>{const q=await K7rel.make('Это тестовый ответ ассистента про погоду и планы на выходные, достаточно длинный.');K7rel.put(q);const bs=[...document.querySelectorAll('#k7-rel .k7-chip')];return JSON.stringify({q:q,n:K7rel.chips(),minh:bs.length?Math.min(...bs.map(x=>x.getBoundingClientRect().height)):-1})})()""",
'pdf':"""(async()=>{K7sel.show('Тестовый фрагмент документа для проверки');const b=document.querySelector('#k7-sel button').getBoundingClientRect();return JSON.stringify({on:document.getElementById('k7-sel').classList.contains('on'),h:b.height})})()""",
'soul':"""(async()=>{const s=K7pres.state();const bh=document.querySelector('#k7-pa').getBoundingClientRect().height;return JSON.stringify({line:s.line,bh:bh,box:!!document.getElementById('k7-pres')})})()"""}
async def m():
  async with async_playwright() as p:
    b=await p.chromium.launch(args=[])
    for w,h in((1440,900),(390,844)):
      for pg_ in T:
        pg=await b.new_page(viewport={'width':w,'height':h});errs=[];pg.on('pageerror',lambda e:errs.append(str(e)[:140]))
        try:
          await pg.goto('http://127.0.0.1:8091/web/%s.html'%pg_,wait_until='domcontentloaded',timeout=40000);await pg.wait_for_function('window.%s'%T[pg_],timeout=15000);await pg.wait_for_timeout(1500)
          r=await asyncio.wait_for(pg.evaluate(JS[pg_]),60);print('QA',w,pg_,r,'errs',errs[:3])
        except Exception as e: print('QA EXC',w,pg_,str(e)[:300],errs[:3])
        await pg.close()
    await b.close()
asyncio.run(m())
QAEOF
echo "K7 f2 done"
