echo "C300: k5_a_2"
S=/workspace/nox/web/site; cd $S
TS=$(date +%s)
cat > nox-k5-xray.js <<'K5EOF'
/* K5 №81 (cinema): X-Ray: пауза кадра -> «кто в кадре» (кадр в canvas + название/время в запрос K4.ask) */
(function(){
 let d,vid=null;
 function cur(){ return document.querySelector('video')||vid }
 function open(){ if(!d){d=K4.modal('k5-xr-d','X-Ray: кто в кадре');
   d.innerHTML='<label class="k4-muted" for="k5-xt">Название фильма или сцены</label><input id="k5-xt" class="k4-in" style="width:100%" placeholder="Например: Интерстеллар">'+
   '<div class="k5-xr"><label class="k4-btn" for="k5-xf">Выбрать видео<input type="file" id="k5-xf" accept="video/*" hidden></label><button class="k4-btn pri" type="button" id="k5-xg">Пауза и X-Ray</button></div>'+
   '<video id="k5-xv" class="k5-xv" controls playsinline></video><canvas id="k5-xc" width="320" height="180" class="k5-xcv" aria-label="Стоп-кадр"></canvas><div class="k4-out" id="k5-xo"></div>';
   const v=d.querySelector('#k5-xv'),c=d.querySelector('#k5-xc'),o=d.querySelector('#k5-xo');
   d.querySelector('#k5-xf').addEventListener('change',function(e){const f=e.target.files[0];if(f){v.src=URL.createObjectURL(f);vid=v;d.querySelector('#k5-xt').value=d.querySelector('#k5-xt').value||f.name.replace(/\.[^.]+$/,'')}});
   d.querySelector('#k5-xg').addEventListener('click',function(){const x=cur()||v;try{x.pause()}catch(e){}
    const t=Math.round(x.currentTime||0),ts=Math.floor(t/60)+':'+String(t%60).padStart(2,'0');
    let tone='';try{const g=c.getContext('2d');g.drawImage(x,0,0,c.width,c.height);const p=g.getImageData(0,0,32,18).data;let r=0,gg=0,b=0,n=p.length/4;for(let i=0;i<p.length;i+=4){r+=p[i];gg+=p[i+1];b+=p[i+2]}tone='; средний цвет кадра rgb('+Math.round(r/n)+','+Math.round(gg/n)+','+Math.round(b/n)+')'}catch(e){tone=''}
    const name=d.querySelector('#k5-xt').value.trim()||(document.title||'фильм');
    K4.ask('X-Ray: «'+name+'», пауза на '+ts+tone+'. Назови актёров основного состава и роли, затем в 2 фразах скажи, что обычно происходит в этой части сюжета. Если не уверен, так и скажи.',o)})}
  d.show()}
 K4.ready(function(){K4.fab('k5-xr-b','X-Ray','scan',open)});
})();
K5EOF
cat > nox-k5-xray.css <<'K5EOF'
.k5-xr{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0}
.k5-xv{width:100%;max-height:34vh;border-radius:12px;background:#000}
.k5-xcv{width:160px;height:auto;border-radius:8px;margin-top:8px}
K5EOF
cat > nox-k5-diff.js <<'K5EOF'
/* K5 №82 (assistant): диффы правок ИИ: красные/зелёные строки с принять/отклонить на каждый блок */
(function(){
 let d,orig=[],hunks=[];
 function diff(a,b){ const n=a.length,m=b.length,L=[];for(let i=0;i<=n;i++)L.push(new Array(m+1).fill(0));
  for(let i=n-1;i>=0;i--)for(let j=m-1;j>=0;j--)L[i][j]=a[i]===b[j]?L[i+1][j+1]+1:Math.max(L[i+1][j],L[i][j+1]);
  const ops=[];let i=0,j=0;while(i<n&&j<m){if(a[i]===b[j]){ops.push(['=',a[i]]);i++;j++}else if(L[i+1][j]>=L[i][j+1]){ops.push(['-',a[i++]])}else ops.push(['+',b[j++]])}
  while(i<n)ops.push(['-',a[i++]]);while(j<m)ops.push(['+',b[j++]]);
  const out=[];ops.forEach(function(o){const l=out[out.length-1];if(o[0]==='='){out.push({eq:o[1]})}else{if(l&&!l.eq){(o[0]==='-'?l.del:l.add).push(o[1])}else{const h={del:[],add:[],st:'?'};(o[0]==='-'?h.del:h.add).push(o[1]);out.push(h)}}});return out}
 function result(){ const r=[];hunks.forEach(function(h){if(h.eq!==undefined)r.push(h.eq);else if(h.st==='ok')r.push.apply(r,h.add);else r.push.apply(r,h.del)});return r.join('\n')}
 function paint(){ const box=d.querySelector('#k5-dfv');box.innerHTML='';
  hunks.forEach(function(h,i){const e=document.createElement('div');
   if(h.eq!==undefined){e.className='k5-dl';e.textContent='  '+h.eq}
   else{e.className='k5-dh'+(h.st!=='?'?' done':'');e.innerHTML=h.del.map(function(x){return '<div class="k5-dl del">- '+K4.esc(x)+'</div>'}).join('')+h.add.map(function(x){return '<div class="k5-dl add">+ '+K4.esc(x)+'</div>'}).join('')+
    (h.st==='?'?'<div class="k5-da"><button class="k4-btn pri" type="button" data-a="ok" data-i="'+i+'">Принять</button><button class="k4-btn" type="button" data-a="no" data-i="'+i+'">Отклонить</button></div>':'<small class="k4-muted">'+(h.st==='ok'?'принято':'отклонено')+'</small>')}
   box.appendChild(e)});
  d.querySelector('#k5-dfr').value=result()}
 function build(a,b){ hunks=diff(a.split('\n'),b.split('\n'));paint()}
 function open(){ if(!d){d=K4.modal('k5-df-d','Правка ИИ: диф');
   d.innerHTML='<label class="k4-muted" for="k5-dfa">Исходный текст или код</label><textarea id="k5-dfa" class="k4-in" rows="5" style="width:100%;padding:10px"></textarea>'+
   '<label class="k4-muted" for="k5-dfi">Что изменить</label><input id="k5-dfi" class="k4-in" style="width:100%" placeholder="Исправь ошибки и сократи">'+
   '<div class="k5-da"><button class="k4-btn pri" type="button" id="k5-dfg">Предложить правку</button><button class="k4-btn" type="button" id="k5-dfa1">Принять всё</button><button class="k4-btn" type="button" id="k5-dfc">Копировать результат</button></div>'+
   '<div id="k5-dfv" class="k5-dfv"></div><label class="k4-muted" for="k5-dfr">Результат</label><textarea id="k5-dfr" class="k4-in" rows="4" style="width:100%;padding:10px" readonly></textarea><div id="k5-dfo" hidden></div>';
   d.querySelector('#k5-dfg').addEventListener('click',async function(){const a=d.querySelector('#k5-dfa').value;if(!a.trim())return;const o=d.querySelector('#k5-dfo');
    d.querySelector('#k5-dfv').textContent='NOX правит…';
    const t=await K4.ask('Правка: '+(d.querySelector('#k5-dfi').value||'улучши текст')+'. Верни ТОЛЬКО исправленный текст целиком, без пояснений и без обрамления.\n\n'+a,o);
    build(a,(t||o.textContent||a).replace(/^```\w*\n?|```$/g,''))});
   d.querySelector('#k5-dfv').addEventListener('click',function(e){const b=e.target.closest('button[data-i]');if(!b)return;hunks[+b.dataset.i].st=b.dataset.a;paint()});
   d.querySelector('#k5-dfa1').addEventListener('click',function(){hunks.forEach(function(h){if(h.eq===undefined&&h.st==='?')h.st='ok'});paint()});
   d.querySelector('#k5-dfc').addEventListener('click',function(){const r=d.querySelector('#k5-dfr');r.select();try{navigator.clipboard.writeText(r.value)}catch(e){}});
   window.K5diff={build:build,hunks:function(){return hunks},result:result}}
  d.show()}
 K4.ready(function(){K4.fab('k5-df-b','Диф правки','git-compare',open)});
})();
K5EOF
cat > nox-k5-diff.css <<'K5EOF'
.k5-dfv{margin:10px 0;font-family:ui-monospace,Menlo,monospace;font-size:12px;max-height:34vh;overflow:auto;border-radius:10px;background:rgba(0,0,0,.35);padding:6px}
.k5-dl{white-space:pre-wrap;padding:2px 6px;color:#cbbfb6}
.k5-dl.del{background:rgba(255,80,70,.22);color:#ffb4ac}.k5-dl.add{background:rgba(70,200,110,.2);color:#a8f0c0}
.k5-dh{margin:4px 0;border-left:3px solid #e9b465;padding-left:4px}.k5-dh.done{opacity:.6}
.k5-da{display:flex;flex-wrap:wrap;gap:8px;margin:8px 0}
K5EOF
cat > nox-k5-see.js <<'K5EOF'
/* K5 №83 (voice): «что это»: камера в голосовом диалоге; кадр + голос/текст-подпись -> K4.ask (NOX получает цвет/яркость кадра и вашу подпись; прямого зрения у чата нет) */
(function(){
 let d,stream=null;
 function stop(){ if(stream){stream.getTracks().forEach(function(t){t.stop()});stream=null} }
 function open(){ if(!d){d=K4.modal('k5-se-d','Что это');
   d.innerHTML='<video id="k5-sv" class="k5-sv" playsinline muted></video><canvas id="k5-sc" width="64" height="48" hidden></canvas><div class="k5-sa"><button class="k4-btn" type="button" id="k5-ss">Включить камеру</button><button class="k4-btn" type="button" id="k5-sm">Сказать подпись</button></div>'+
   '<input id="k5-st" class="k4-in" style="width:100%" aria-label="Подпись к кадру" placeholder="Что вы показываете? (по желанию)"><div class="k5-sa"><button class="k4-btn pri" type="button" id="k5-sg">Что это?</button></div><div class="k4-out" id="k5-so"></div>';
   const v=d.querySelector('#k5-sv'),c=d.querySelector('#k5-sc'),o=d.querySelector('#k5-so');
   d.querySelector('#k5-ss').addEventListener('click',async function(){ if(stream){stop();v.srcObject=null;this.textContent='Включить камеру';return}
    try{stream=await navigator.mediaDevices.getUserMedia({video:{facingMode:'environment'}});v.srcObject=stream;await v.play();this.textContent='Выключить камеру'}catch(e){o.textContent='Камера недоступна: '+e.message}});
   d.querySelector('#k5-sm').addEventListener('click',function(){const R=window.SpeechRecognition||window.webkitSpeechRecognition;if(!R){o.textContent='Распознавание речи недоступно: введите подпись текстом.';return}
    const r=new R();r.lang='ru-RU';r.onresult=function(e){d.querySelector('#k5-st').value=e.results[0][0].transcript};r.onerror=function(e){o.textContent='Голос: '+e.error};r.start()});
   d.querySelector('#k5-sg').addEventListener('click',function(){let info='кадра нет (камера выключена)';
    if(stream&&v.videoWidth){const g=c.getContext('2d');g.drawImage(v,0,0,c.width,c.height);const p=g.getImageData(0,0,c.width,c.height).data;let r=0,gg=0,b=0,n=p.length/4;for(let i=0;i<p.length;i+=4){r+=p[i];gg+=p[i+1];b+=p[i+2]}info='средний цвет кадра rgb('+Math.round(r/n)+','+Math.round(gg/n)+','+Math.round(b/n)+'), яркость '+Math.round((r+gg+b)/n/7.65)+'%'}
    const cap=d.querySelector('#k5-st').value.trim();
    K4.ask('Пользователь спрашивает «что это?» и показывает предмет камерой. Данные: '+info+'; подпись: '+(cap||'нет')+'. Скажи, что это, вероятнее всего, и какие уточнения нужны. Коротко, честно про неуверенность.',o)});
   d.addEventListener('sl-after-hide',function(e){if(e.target===d){stop();v.srcObject=null}})}
  d.show()}
 K4.ready(function(){K4.fab('k5-se-b','Что это','camera',open)});
})();
K5EOF
cat > nox-k5-see.css <<'K5EOF'
.k5-sv{width:100%;max-height:36vh;border-radius:12px;background:#000;object-fit:cover}
.k5-sa{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0}
K5EOF
cat > nox-k5-mascot.js <<'K5EOF'
/* K5 №84 (chat): талисман NOX реагирует на состояния: ждёт / слушает (фокус в поле) / думает (идёт /api/chat) / говорит. Векторный, без внешних .riv (в vendor/rive нет файла анимации). */
(function(){
 K4.ready(function(){ if(document.getElementById('k5-mc'))return;
  const m=document.createElement('div');m.id='k5-mc';m.className='k5-mc';m.setAttribute('role','img');m.setAttribute('aria-label','Талисман NOX: ожидает');m.dataset.state='idle';
  m.innerHTML='<svg viewBox="0 0 80 80" width="64" height="64" aria-hidden="true"><circle class="k5-bd" cx="40" cy="42" r="26"/><circle class="k5-ey" cx="30" cy="38" r="4"/><circle class="k5-ey" cx="50" cy="38" r="4"/><path class="k5-mo" d="M30 54 Q40 60 50 54" fill="none"/><line class="k5-an" x1="40" y1="16" x2="40" y2="8"/><circle class="k5-at" cx="40" cy="7" r="3"/></svg><span class="k5-lb">ждёт</span>';
  document.body.appendChild(m);
  const L={idle:'ждёт',listen:'слушает',think:'думает',speak:'говорит'};
  function set(s){ if(m.dataset.state===s)return;m.dataset.state=s;m.setAttribute('aria-label','Талисман NOX: '+L[s]);m.querySelector('.k5-lb').textContent=L[s]}
  let pend=0,t=0;
  const f=window.fetch;window.fetch=function(u){const url=String(u&&u.url||u);const isChat=url.indexOf('/api/chat')>=0;
   if(isChat){pend++;set('think')}
   const p=f.apply(this,arguments);
   if(isChat)p.then(function(r){set('speak');clearTimeout(t);t=setTimeout(function(){pend=Math.max(0,pend-1);if(!pend)set(document.activeElement&&/INPUT|TEXTAREA/.test(document.activeElement.tagName)?'listen':'idle')},2500);return r},function(){pend=Math.max(0,pend-1);set('idle')});
   return p};
  document.addEventListener('focusin',function(e){if(!pend&&/INPUT|TEXTAREA/.test(e.target.tagName))set('listen')});
  document.addEventListener('focusout',function(){if(!pend)set('idle')});
  window.K5mascot={set:set,state:function(){return m.dataset.state}}});
})();
K5EOF
cat > nox-k5-mascot.css <<'K5EOF'
.k5-mc{position:fixed;right:12px;bottom:160px;z-index:44;min-width:44px;min-height:44px;display:flex;flex-direction:column;align-items:center;pointer-events:none}
.k5-mc svg{filter:drop-shadow(0 0 10px rgba(233,180,101,.45))}
.k5-bd{fill:#2a1d1d;stroke:#e9b465;stroke-width:3}.k5-ey{fill:#efe6df;transform-box:fill-box;transform-origin:center}
.k5-mo{stroke:#efe6df;stroke-width:3;stroke-linecap:round}.k5-an{stroke:#e9b465;stroke-width:2}.k5-at{fill:#e9b465}
.k5-lb{font-size:12px;color:#cbbfb6}
.k5-mc[data-state=idle] svg{animation:k5-fl 3.2s ease-in-out infinite}
.k5-mc[data-state=idle] .k5-ey{animation:k5-bl 4s infinite}
.k5-mc[data-state=listen] .k5-ey{transform:scale(1.4)}.k5-mc[data-state=listen] .k5-at{animation:k5-pu 1s infinite}
.k5-mc[data-state=think] svg{animation:k5-sw 1.2s ease-in-out infinite}.k5-mc[data-state=think] .k5-ey{transform:translateX(3px) scaleY(.5)}
.k5-mc[data-state=speak] .k5-mo{animation:k5-tk .35s infinite alternate}
@keyframes k5-fl{50%{transform:translateY(-4px)}}@keyframes k5-bl{0%,92%,100%{transform:scaleY(1)}96%{transform:scaleY(.1)}}
@keyframes k5-pu{50%{transform:scale(1.8)}}@keyframes k5-sw{25%{transform:rotate(-6deg)}75%{transform:rotate(6deg)}}
@keyframes k5-tk{to{d:path("M30 54 Q40 66 50 54")}}
@media(prefers-reduced-motion:reduce){.k5-mc *{animation:none!important}}
K5EOF
add(){ f=$1.html; [ -f $f ] || { echo "no $f"; return; }
 grep -q "nox-k5-$2.js" $f && { echo "have $f $2"; return; }
 cp $f $f.bak_k5_$TS; tag=""
 grep -q "nox-k4-core.js" $f || tag="<script src=\"./nox-k4-core.js?v=k4a\" defer></script>"
 tag="$tag<link rel=\"stylesheet\" href=\"./nox-k5-$2.css?v=k5a\"><script src=\"./nox-k5-$2.js?v=k5a\" defer></script>"
 python3 - "$f" "$tag" <<'PY'
import sys
f,t=sys.argv[1],sys.argv[2]
s=open(f,encoding='utf-8').read();i=s.rfind('</body>')
open(f,'w',encoding='utf-8').write(s[:i]+t+s[i:] if i>=0 else s+t)
PY
 echo "added $2 -> $f"; }
add cinema xray
grep -q "K5: №81 " qa/rework/cinema.fixed 2>/dev/null || echo "K5: №81 X-Ray" >> qa/rework/cinema.fixed
add assistant diff
grep -q "K5: №82 " qa/rework/assistant.fixed 2>/dev/null || echo "K5: №82 диф правок ИИ" >> qa/rework/assistant.fixed
add voice see
grep -q "K5: №83 " qa/rework/voice.fixed 2>/dev/null || echo "K5: №83 что это" >> qa/rework/voice.fixed
add chat mascot
grep -q "K5: №84 " qa/rework/chat.fixed 2>/dev/null || echo "K5: №84 талисман состояний" >> qa/rework/chat.fixed
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python
timeout 250 $PY /tmp/k2_qa.py cinema assistant voice chat 2>&1 | tail -12
$PY - <<'QAEOF'
import asyncio,json
from playwright.async_api import async_playwright
C=[["cinema", "xray", "(async()=>{const f=document.getElementById('k5-xr-b');if(!f)return 'NO';f.click();await new Promise(r=>setTimeout(r,400));document.getElementById('k5-xt').value='Тест';document.getElementById('k5-xg').click();await new Promise(r=>setTimeout(r,2500));return JSON.stringify({out:document.getElementById('k5-xo').textContent.slice(0,60),h:document.getElementById('k5-xg').offsetHeight})})()"], ["assistant", "diff", "(async()=>{const f=document.getElementById('k5-df-b');if(!f)return 'NO';f.click();await new Promise(r=>setTimeout(r,400));K5diff.build('a\\nb\\nc','a\\nB\\nc');const h=K5diff.hunks().filter(x=>x.eq===undefined).length;const bt=document.querySelector('#k5-dfv button[data-a=ok]');bt.click();return JSON.stringify({hunks:h,res:K5diff.result(),h:bt.offsetHeight,add:document.querySelectorAll('.k5-dl.add').length,del:document.querySelectorAll('.k5-dl.del').length})})()"], ["voice", "see", "(async()=>{const f=document.getElementById('k5-se-b');if(!f)return 'NO';f.click();await new Promise(r=>setTimeout(r,400));document.getElementById('k5-st').value='чашка';document.getElementById('k5-sg').click();await new Promise(r=>setTimeout(r,2500));return JSON.stringify({out:document.getElementById('k5-so').textContent.slice(0,60),h:document.getElementById('k5-sg').offsetHeight})})()"], ["chat", "mascot", "(async()=>{const m=document.getElementById('k5-mc');if(!m)return 'NO';K5mascot.set('think');const a=K5mascot.state();K5mascot.set('speak');return JSON.stringify({a,b:K5mascot.state(),label:m.getAttribute('aria-label'),w:m.offsetWidth,h:m.offsetHeight})})()"]]
async def m():
  async with async_playwright() as p:
    b=await p.chromium.launch(args=[])
    for w,h in((1440,900),(390,844)):
      for u,f,js in C:
        pg=await b.new_page(viewport={'width':w,'height':h});errs=[];pg.on('pageerror',lambda e:errs.append(str(e)[:120]))
        try:
          await pg.goto('http://127.0.0.1:8091/web/'+u+'.html',wait_until='domcontentloaded',timeout=40000);await pg.wait_for_timeout(3500)
          r=await pg.evaluate(js)
          if f=='canvas' and r!='NO':
            j=json.loads(r);await pg.mouse.move(j['x']+20,j['y']+20);await pg.mouse.down();await pg.mouse.move(j['x']+120,j['y']+80,steps=8);await pg.mouse.up();await pg.wait_for_timeout(400)
            r+=' '+await pg.evaluate("JSON.stringify({cover:K5canvas.stats().cover,res:(()=>{const c=document.getElementById('k5-cb'),d=c.getContext('2d').getImageData(0,0,c.width,c.height).data;let n=0;for(let i=3;i<d.length;i+=4)if(d[i]>0)n++;return n})()})")
        except Exception as e: r='EXC '+str(e)[:160]
        print(w,u,f,r,'errs',len(errs),errs[:2])
        await pg.close()
    await b.close()
asyncio.run(m())
QAEOF
