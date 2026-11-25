echo "C300: k3_b1"
S=/workspace/nox/web/site; cd $S
TS=$(date +%s)
cat > nox-k3-core.js <<'EOF'
/* K3 core: общий помощник. K3.ask(prompt, el) -> поток из /api/chat (NDJSON) в el.textContent; K3.esc; K3.need(fn) */
(function(){ if(window.K3)return; window.K3={
 esc:function(s){return String(s==null?'':s).replace(/[&<>"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})},
 ask:async function(prompt,el){ el.textContent='…'; let acc='';
  try{const r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({model:'nox-helion:latest',stream:true,nox_mode:'fast',conversation_id:'k3',messages:[{role:'user',content:prompt}]})});
   if(!r.ok)throw new Error('HTTP '+r.status);const rd=r.body.getReader(),dec=new TextDecoder();let buf='';
   for(;;){const x=await rd.read();if(x.done)break;buf+=dec.decode(x.value,{stream:true});let i;
    while((i=buf.indexOf('\n'))>=0){const ln=buf.slice(0,i).trim();buf=buf.slice(i+1);if(!ln)continue;let o;try{o=JSON.parse(ln)}catch(e){continue}
     const c=(o.message&&o.message.content)||(typeof o.response==='string'?o.response:'');if(c){acc+=c;el.textContent=acc}}}
   if(!acc)el.textContent='NOX занят, повторите позже.';}catch(e){el.textContent='NOX недоступен: '+e.message}
  return acc},
 ready:function(sel,fn,ms){let n=0;const t=setInterval(function(){const e=document.querySelector(sel);if(e){clearInterval(t);fn(e)}else if(++n>(ms||80))clearInterval(t)},250)}
};})();
EOF
# ---- 1 voice orb (переиспользует nox-chat-fx.js)
cat > nox-k3-orb.css <<'EOF'
#k3-orb{position:relative;margin:0 0 16px;padding:16px;border-radius:20px;background:rgba(20,15,15,.9);border:1px solid rgba(255,255,255,.12);display:flex;flex-direction:column;align-items:center;gap:12px;overflow:hidden}
#k3-orb #stage{position:absolute;inset:0;pointer-events:none}
#k3-orb .tg-thoughts{position:absolute;inset:0;width:100%;height:100%;opacity:.55}
#k3-orb .tg-head{display:none}
#k3-orb .tg-av{position:relative;z-index:2;width:200px;height:200px;border-radius:50%;cursor:pointer;display:block}
#k3-orb .tg-orb{width:100%;height:100%;display:block}
#k3-orb sl-button{position:relative;z-index:2}
#k3-orb sl-button::part(base){min-height:44px;font-size:14px}
#k3-orb .k3-cap{position:relative;z-index:2;font-size:12px;color:#cbbfb6}
EOF
cat > nox-k3-orb.js <<'EOF'
/* K3 №1: голосовой шар с волнообразной амплитудой на voice. Переиспользует nox-chat-fx.js (орб three + микрофон + VAD), своего шара нет. */
(function(){
 function go(){const host=document.querySelector('#page .wrap')||document.getElementById('page');if(!host||document.getElementById('k3-orb'))return;
  const b=document.createElement('section');b.id='k3-orb';
  b.innerHTML='<div id="stage"></div><div class="tg-head"></div><div class="tg-av" role="button" tabindex="0" aria-label="Голосовой шар NOX"></div><sl-button size="large" pill id="k3-orb-b">Слушать</sl-button><span class="k3-cap">Шар дышит от голоса: нажмите, чтобы он слушал микрофон</span>';
  host.insertBefore(b,host.children[1]||null);
  import('/web/nox-chat-fx.js?v=k3').catch(function(){});
  const btn=b.querySelector('#k3-orb-b');
  btn.addEventListener('click',function(){const av=b.querySelector('.tg-av');if(av)av.click()});
  new MutationObserver(function(){btn.textContent=document.body.classList.contains('tg-listen')?'Остановить':'Слушать'}).observe(document.body,{attributes:true,attributeFilter:['class']});
 }
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',go);else go();
})();
EOF
# ---- 2 chat screenshot
cat > nox-k3-shot.css <<'EOF'
#k3-shot{min-width:44px;min-height:44px;display:inline-flex;align-items:center;justify-content:center;background:none;border:0;color:inherit;cursor:pointer;border-radius:12px;font-size:16px}
#k3-shot:hover{background:rgba(255,255,255,.1)}
#k3-chip{display:flex;align-items:center;gap:8px;margin:8px 0;padding:6px 10px;border-radius:12px;background:rgba(255,255,255,.08);font-size:12px;color:#cbbfb6;width:fit-content}
#k3-chip img{height:44px;border-radius:6px}
#k3-chip button{min-width:44px;min-height:44px;background:none;border:0;color:inherit;cursor:pointer;font-size:16px}
EOF
cat > nox-k3-shot.js <<'EOF'
/* K3 №2: «посмотри экран»: скриншот раздела (html-to-image) + видимый текст уходят в поле ввода чата. Связь: /api/chat через штатную отправку. */
(function(){
 K=window.K3;
 function go(att){if(document.getElementById('k3-shot'))return;
  const b=document.createElement('button');b.type='button';b.id='k3-shot';b.title='Посмотри экран: приложить снимок раздела';b.setAttribute('aria-label','Приложить снимок экрана');b.innerHTML='<sl-icon library="tabler" name="camera"></sl-icon>';
  att.insertAdjacentElement('afterend',b);
  b.addEventListener('click',async function(){
   b.disabled=true;let url='';
   try{const m=await import('./vendor/html-to-image/html-to-image.esm.js');url=await m.toJpeg(document.getElementById('app')||document.body,{quality:.5,pixelRatio:.5,filter:function(n){return n.tagName!=='CANVAS'&&n.tagName!=='VIDEO'}})}catch(e){}
   const txt=((document.getElementById('msgs')||document.body).innerText||'').replace(/\s+/g,' ').trim().slice(-1200);
   const inp=document.getElementById('input');
   if(inp){inp.value='Посмотри на экран раздела «чат». Видимый текст: '+txt+'\n\nЧто здесь важно?';inp.dispatchEvent(new Event('input',{bubbles:true}));inp.focus()}
   const old=document.getElementById('k3-chip');if(old)old.remove();
   const c=document.createElement('div');c.id='k3-chip';c.innerHTML=(url?'<img alt="снимок" src="'+url+'">':'')+'<span>снимок экрана приложен</span><button type="button" aria-label="Убрать снимок">×</button>';
   c.querySelector('button').onclick=function(){c.remove()};
   const f=document.getElementById('composer');if(f)f.insertAdjacentElement('beforebegin',c);
   b.disabled=false});}
 let n=0;const t=setInterval(function(){const a=document.getElementById('btnAttach');if(a){clearInterval(t);go(a)}else if(++n>80)clearInterval(t)},250);
})();
EOF
# ---- 3 finance drill-down
cat > nox-k3-drill.css <<'EOF'
#k3-drill{margin:0 0 16px;padding:14px;border-radius:18px;background:rgba(20,15,15,.95);border:1px solid rgba(255,255,255,.12)}
#k3-drill h3{margin:0 0 8px;font-size:16px;font-weight:400;color:#efe6df}
#k3-drill .k3-chips{display:flex;flex-wrap:wrap;gap:8px}
#k3-drill sl-button::part(base){min-height:44px;font-size:14px}
#k3-dr-d::part(panel){background:rgba(24,18,18,.94);backdrop-filter:blur(18px)}
#k3-dr-d ul{list-style:none;margin:0 0 12px;padding:0}
#k3-dr-d li{display:flex;justify-content:space-between;gap:8px;padding:10px 0;border-bottom:1px solid rgba(255,255,255,.1);font-size:14px}
#k3-dr-d small{display:block;font-size:12px;color:#a89c93}
#k3-dr-ai{white-space:pre-wrap;font-size:14px;margin-top:12px;color:#efe6df}
EOF
cat > nox-k3-drill.js <<'EOF'
/* K3 №3: drill-down по категориям расходов: клик по сегменту раскрывает строки под ним; «Объяснить выброс» -> /api/chat */
(function(){
 function tx(){for(let i=0;i<localStorage.length;i++){const k=localStorage.key(i);try{const a=JSON.parse(localStorage.getItem(k));if(Array.isArray(a)&&a.length&&a[0]&&'amt' in a[0]&&'cat' in a[0])return a}catch(e){}}return[]}
 const rub=function(v){return Math.round(v).toLocaleString('ru-RU')+' ₽'};
 function load(src){return new Promise(function(ok){if(window.K3)return ok();const s=document.createElement('script');s.src=src;s.onload=ok;s.onerror=ok;document.head.appendChild(s)})}
 let dr;
 function open(cat,rows){if(dr)dr.remove();dr=document.createElement('sl-drawer');dr.id='k3-dr-d';dr.label=cat+' · '+rows.length+' записей';dr.placement='end';
  const mx=rows.slice().sort(function(a,b){return Math.abs(b.amt)-Math.abs(a.amt)})[0];
  dr.innerHTML='<ul>'+rows.map(function(t){return'<li><div><b>'+K3.esc(t.cat)+'</b><small>'+K3.esc(t.d)+(t.note?' · '+K3.esc(t.note):'')+'</small></div><strong>'+rub(t.amt)+'</strong></li>'}).join('')+'</ul><sl-button size="large" variant="primary" id="k3-dr-ex">Объяснить выброс</sl-button><div id="k3-dr-ai"></div>';
  document.body.appendChild(dr);dr.show();dr.addEventListener('sl-after-hide',function(e){if(e.target===dr)dr.remove()});
  dr.querySelector('#k3-dr-ex').addEventListener('click',function(){K3.ask('Объясни самый крупный платёж в категории «'+cat+'»: '+rub(mx.amt)+' от '+mx.d+(mx.note?' ('+mx.note+')':'')+'. Все записи категории: '+JSON.stringify(rows.slice(0,25).map(function(t){return[t.d,t.amt]}))+'. Это выброс? Ответь коротко.',dr.querySelector('#k3-dr-ai'))})}
 function render(){const host=document.getElementById('fiMain')||document.getElementById('page');const all=tx().filter(function(t){return t.amt<0});
  let b=document.getElementById('k3-drill');if(!b){b=document.createElement('section');b.id='k3-drill';b.innerHTML='<h3>Расходы по категориям: нажмите, чтобы раскрыть</h3><div class="k3-chips"></div>';host.insertBefore(b,host.firstChild)}
  const by={};all.forEach(function(t){(by[t.cat]=by[t.cat]||[]).push(t)});const ks=Object.keys(by).sort(function(a,c){return by[c].reduce(function(s,t){return s-t.amt},0)-by[a].reduce(function(s,t){return s-t.amt},0)});
  const ch=b.querySelector('.k3-chips');ch.innerHTML='';
  if(!ks.length){ch.innerHTML='<span class="ds-empty">Пока нет расходов: добавьте запись справа</span>';return}
  ks.forEach(function(k){const s=document.createElement('sl-button');s.pill=true;s.size='large';s.textContent=k+' · '+rub(by[k].reduce(function(x,t){return x-t.amt},0));s.addEventListener('click',function(){open(k,by[k].slice().reverse())});ch.appendChild(s)})}
 load('./nox-k3-core.js').then(function(){K3.ready('#fiList',function(l){render();new MutationObserver(render).observe(l,{childList:true})},120)});
})();
EOF
# ---- 4 knowledge studio tiles
cat > nox-k3-studio.css <<'EOF'
#k3-st{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:16px 0}
@media(max-width:800px){#k3-st{grid-template-columns:repeat(2,1fr)}}
#k3-st sl-card{--border-radius:16px}
#k3-st sl-card::part(base){background:rgba(20,15,15,.92);border:1px solid rgba(255,255,255,.12);min-height:44px}
#k3-st button.t{all:unset;box-sizing:border-box;display:block;width:100%;min-height:88px;padding:4px;cursor:pointer;color:#efe6df;font-size:14px}
#k3-st button.t:focus-visible{outline:2px solid #e9b465}
#k3-st b{display:block;font-size:16px;font-weight:400;margin-bottom:4px}
#k3-st small{font-size:12px;color:#a89c93}
#k3-st-d::part(panel){background:rgba(24,18,18,.94);backdrop-filter:blur(18px)}
#k3-st-out{white-space:pre-wrap;font-size:14px;margin-top:12px;color:#efe6df}
EOF
cat > nox-k3-studio.js <<'EOF'
/* K3 №4: Studio-плитки (аудио, видео, карта, отчёт) над результатами. Связь: /api/chat, тема берётся из поля или заголовка */
(function(){
 const T=[['Аудио-обзор','сценарий подкаста на двоих','Сделай сценарий аудио-обзора (диалог двух ведущих, 6 реплик) по теме: '],['Видео-обзор','раскадровка из 5 слайдов','Сделай раскадровку видео-обзора из 5 слайдов (заголовок и одна мысль) по теме: '],['Карта','карта-ум из ветвей','Построй карту-ум (иерархия до 3 уровней, отступами) по теме: '],['Отчёт','краткий отчёт с выводами','Напиши краткий отчёт (введение, 3 пункта, вывод) по теме: ']];
 function load(src){return new Promise(function(ok){if(window.K3)return ok();const s=document.createElement('script');s.src=src;s.onload=ok;s.onerror=ok;document.head.appendChild(s)})}
 function go(){const p=document.querySelector('#page .purpose');if(!p||document.getElementById('k3-st'))return;
  const g=document.createElement('div');g.id='k3-st';
  g.innerHTML=T.map(function(t,i){return'<sl-card><button type="button" class="t" data-i="'+i+'"><b>'+t[0]+'</b><small>'+t[1]+'</small></button></sl-card>'}).join('');
  p.insertAdjacentElement('afterend',g);
  const d=document.createElement('sl-dialog');d.id='k3-st-d';d.innerHTML='<sl-input id="k3-st-in" size="large" label="Тема" placeholder="О чём сделать обзор"></sl-input><sl-button id="k3-st-go" size="large" variant="primary" style="margin-top:12px">Сделать</sl-button><div id="k3-st-out"></div>';document.body.appendChild(d);
  let cur=0;g.addEventListener('click',function(e){const b=e.target.closest('button.t');if(!b)return;cur=+b.dataset.i;d.label=T[cur][0];d.querySelector('#k3-st-out').textContent='';d.show()});
  d.querySelector('#k3-st-go').addEventListener('click',function(){const th=(d.querySelector('#k3-st-in').value||'').trim()||'знания и память NOX';K3.ask(T[cur][2]+th,d.querySelector('#k3-st-out'))});}
 load('./nox-k3-core.js').then(function(){if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',go);else go()});
})();
EOF
# ---- 5 news peek
cat > nox-k3-peek.css <<'EOF'
a.nw-cd,a.nw-lead,a.nw-sl{position:relative}
.k3-peek{position:absolute;top:8px;right:8px;z-index:3;min-width:44px;min-height:44px;border-radius:50%;border:1px solid rgba(255,255,255,.25);background:rgba(20,15,15,.75);color:#efe6df;cursor:pointer;font-size:16px;backdrop-filter:blur(8px)}
.k3-peek:hover{background:rgba(233,180,101,.35)}
#k3-pk::part(panel){background:rgba(24,18,18,.94);backdrop-filter:blur(18px)}
#k3-pk-sum{font-size:14px;color:#cbbfb6;margin:0 0 12px}
#k3-pk-ai{white-space:pre-wrap;font-size:14px;margin-top:12px;color:#efe6df}
EOF
cat > nox-k3-peek.js <<'EOF'
/* K3 №5: Peek: предпросмотр новости в окне без ухода со страницы; «Кратко по ссылке» -> /api/chat */
(function(){
 function load(src){return new Promise(function(ok){if(window.K3)return ok();const s=document.createElement('script');s.src=src;s.onload=ok;s.onerror=ok;document.head.appendChild(s)})}
 function decorate(root){root.querySelectorAll('a.nw-cd,a.nw-lead,a.nw-sl').forEach(function(a){if(a.querySelector('.k3-peek'))return;const b=document.createElement('button');b.type='button';b.className='k3-peek';b.title='Peek: предпросмотр';b.setAttribute('aria-label','Предпросмотр');b.textContent='👁';a.appendChild(b)})}
 let d;
 function open(a){if(d)d.remove();const h=a.querySelector('h3,h4,.t');const title=(h?h.textContent:a.textContent).trim().slice(0,200);const pp=a.querySelector('p');const sum=pp?pp.textContent.trim():'';
  d=document.createElement('sl-dialog');d.id='k3-pk';d.label=title;
  d.innerHTML='<p id="k3-pk-sum">'+K3.esc(sum||'Краткого описания нет.')+'</p><sl-button size="large" variant="primary" id="k3-pk-b">Кратко по ссылке</sl-button> <sl-button size="large" id="k3-pk-o" href="'+K3.esc(a.href)+'" target="_blank">Открыть</sl-button><div id="k3-pk-ai"></div>';
  document.body.appendChild(d);d.show();d.addEventListener('sl-after-hide',function(e){if(e.target===d)d.remove()});
  d.querySelector('#k3-pk-b').addEventListener('click',function(){K3.ask('Кратко (3 предложения) перескажи новость по ссылке '+a.href+'. Заголовок: '+title+'. '+sum,d.querySelector('#k3-pk-ai'))})}
 function go(){const r=document.getElementById('nwRoot')||document.getElementById('page');decorate(r);new MutationObserver(function(){decorate(r)}).observe(r,{childList:true,subtree:true});
  r.addEventListener('click',function(e){const b=e.target.closest('.k3-peek');if(!b)return;e.preventDefault();e.stopPropagation();open(b.closest('a'))},true)}
 load('./nox-k3-core.js').then(function(){if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',go);else go()});
})();
EOF
add(){ f=$1.html; [ -f $f ] || { echo "no $f"; return; }
 grep -q "nox-k3-$2" $f && { echo "have $f $2"; return; }
 cp $f $f.bak_k3_$TS; tag=""
 [ -f nox-k3-$2.css ] && tag="$tag<link rel=\"stylesheet\" href=\"./nox-k3-$2.css?v=k3a\">"
 [ -f nox-k3-$2.js ] && tag="$tag<script src=\"./nox-k3-$2.js?v=k3a\" defer></script>"
 python3 - "$f" "$tag" <<'PY'
import sys
f,t=sys.argv[1],sys.argv[2]
s=open(f,encoding='utf-8').read();i=s.rfind('</body>')
open(f,'w',encoding='utf-8').write(s[:i]+t+s[i:] if i>=0 else s+t)
PY
 echo "added $2 -> $f"; }
# shot использует K3 не обязательно; core нужен drill/studio/peek (грузят сами)
add voice orb; add chat shot; add finance drill; add knowledge studio; add news peek
echo "K3: №1 голосовой шар (orb, переиспользует nox-chat-fx.js)" >> qa/rework/voice.fixed
echo "K3: №2 «посмотри экран» (shot)" >> qa/rework/chat.fixed
echo "K3: №3 drill-down расходов (drill)" >> qa/rework/finance.fixed
echo "K3: №4 Studio-плитки (studio)" >> qa/rework/knowledge.fixed
echo "K3: №5 Peek новости (peek)" >> qa/rework/news.fixed
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python
timeout 200 $PY /tmp/k2_qa.py voice chat finance knowledge news 2>&1 | tail -12
$PY - <<'PY'
import asyncio
from playwright.async_api import async_playwright
async def m():
  async with async_playwright() as p:
    b=await p.chromium.launch(args=['--use-gl=swiftshader','--enable-unsafe-swiftshader'])
    for w,h in((1440,900),(390,844)):
      pg=await b.new_page(viewport={'width':w,'height':h});errs=[];pg.on('pageerror',lambda e:errs.append(str(e)[:100]))
      async def chk(u,js):
        await pg.goto('http://127.0.0.1:8091/web/'+u+'.html');await pg.wait_for_timeout(3500)
        print(w,u,await pg.evaluate(js))
      await chk('voice',"[!!document.getElementById('k3-orb'),!!document.querySelector('#k3-orb canvas.tg-orb')]")
      await chk('chat',"!!document.getElementById('k3-shot')")
      await chk('finance',"document.querySelectorAll('#k3-drill sl-button').length+'/'+!!document.getElementById('k3-drill')")
      await chk('knowledge',"document.querySelectorAll('#k3-st button.t').length")
      await chk('news',"document.querySelectorAll('.k3-peek').length")
      print(w,'errs',errs)
      await pg.close()
    await b.close()
asyncio.run(m())
PY
exit 0
