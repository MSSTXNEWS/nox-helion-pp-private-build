echo "C300: k5_a_1"
S=/workspace/nox/web/site; cd $S
TS=$(date +%s)
cat > nox-k5-pulse.js <<'K5EOF'
/* K5 №75 (index): плавающая лента «Пульс дня»: факты за день + дайджест NOX (K4.ask) + озвучка speechSynthesis */
(function(){
 function say(t,on){ if(!window.speechSynthesis)return false; speechSynthesis.cancel(); if(!on)return true; const u=new SpeechSynthesisUtterance(t);u.lang='ru-RU';u.rate=1;speechSynthesis.speak(u);return true}
 K4.ready(function(){ if(document.getElementById('k5-pulse'))return;
  const r=document.createElement('div');r.id='k5-pulse';r.className='k5-pulse';
  r.innerHTML='<button class="k4-btn pri" type="button" id="k5-pb" aria-expanded="false" aria-controls="k5-pp">Пульс дня</button>'+
   '<div class="k5-pp" id="k5-pp" hidden><div class="k5-pf" id="k5-pf" aria-live="polite"></div><div class="k4-out" id="k5-po"></div>'+
   '<div class="k5-pa"><button class="k4-btn" type="button" id="k5-pr">Обновить</button><button class="k4-btn" type="button" id="k5-ps">Озвучить</button><button class="k4-btn" type="button" id="k5-px">Стоп</button></div></div>';
  document.body.appendChild(r);
  const b=r.querySelector('#k5-pb'),p=r.querySelector('#k5-pp'),f=r.querySelector('#k5-pf'),o=r.querySelector('#k4-po')||r.querySelector('#k5-po');
  let busy=false,text='';
  async function run(){ if(busy)return;busy=true;
   const t=K4.tasks(),today=K4.ymd(new Date()),open=t.filter(function(x){return x.col!=='done'}),due=open.filter(function(x){return x.due&&x.due<=today}),news=await K4.news();
   f.textContent='Сегодня '+today.slice(8)+'.'+today.slice(5,7)+': задач открыто '+open.length+', срочных '+due.length+', новостей в ленте '+news.length+'.';
   const ctx='Задачи: '+(open.slice(0,8).map(function(x){return x.title}).join('; ')||'нет')+'. Новости: '+(news.slice(0,6).map(function(x){return x.title}).join('; ')||'нет');
   text=await K4.ask('Ты NOX. Дай «пульс дня» в 3-4 коротких предложениях: что нового в организме и что сделать первым. Данные: '+f.textContent+' '+ctx,o);
   busy=false}
  b.addEventListener('click',function(){const s=p.hidden;p.hidden=!s;b.setAttribute('aria-expanded',s);if(s&&!o.textContent)run()});
  r.querySelector('#k5-pr').addEventListener('click',run);
  r.querySelector('#k5-ps').addEventListener('click',function(){if(!say(o.textContent,true))f.textContent='Озвучка недоступна в этом браузере'});
  r.querySelector('#k5-px').addEventListener('click',function(){say('',false)});
 });
})();
K5EOF
cat > nox-k5-pulse.css <<'K5EOF'
.k5-pulse{position:fixed;right:12px;bottom:96px;z-index:46;display:flex;flex-direction:column;align-items:flex-end;gap:8px;max-width:min(380px,calc(100vw - 24px))}
.k5-pp{padding:14px;border-radius:18px;background:rgba(20,15,15,.94);border:1px solid rgba(233,180,101,.4);color:#efe6df;backdrop-filter:blur(12px);max-height:60vh;overflow:auto}
.k5-pp[hidden]{display:none}
.k5-pf{font-size:12px;color:#e9b465;margin-bottom:6px}
.k5-pa{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px}
@media(max-width:600px){.k5-pulse{bottom:84px}}
K5EOF
cat > nox-k5-canvas.js <<'K5EOF'
/* K5 №76 (studio): реалтайм-холст: слева рисуешь, справа сразу результат с эффектом; «Доработай» -> K4.ask */
(function(){
 const FX={neon:'saturate(2.4) brightness(1.3) drop-shadow(0 0 6px #e9b465)',blur:'blur(3px) saturate(1.8)',invert:'invert(1) hue-rotate(160deg)',mono:'grayscale(1) contrast(1.6)'};
 let d,A,B,a,b,draw=false,last=null,raf=0;
 function render(){ raf=0; b.clearRect(0,0,B.width,B.height); b.filter=FX[d.querySelector('#k5-cf').value]||'none'; if(d.querySelector('#k5-cm').checked){b.save();b.translate(B.width,0);b.scale(-1,1);b.drawImage(A,0,0);b.restore()}else b.drawImage(A,0,0); b.filter='none'}
 function sched(){ if(!raf)raf=requestAnimationFrame(render)}
 function pos(e){const r=A.getBoundingClientRect();return[(e.clientX-r.left)*A.width/r.width,(e.clientY-r.top)*A.height/r.height]}
 function stats(){ const w=48,h=36,t=document.createElement('canvas');t.width=w;t.height=h;const c=t.getContext('2d');c.fillStyle='#111';c.fillRect(0,0,w,h);c.drawImage(A,0,0,w,h);const px=c.getImageData(0,0,w,h).data;let n=0,col={};
  for(let i=0;i<px.length;i+=4){if(Math.abs(px[i]-17)+Math.abs(px[i+1]-17)+Math.abs(px[i+2]-17)>40){n++;const k=[px[i],px[i+1],px[i+2]].map(function(v){return v>170?'выс':v>85?'сред':'низ'}).join('/');col[k]=(col[k]||0)+1}}
  return{cover:Math.round(n*100/(w*h)),cols:Object.keys(col).sort(function(x,y){return col[y]-col[x]}).slice(0,3)}}
 function open(){ if(!d){d=K4.modal('k5-cv-d','Реалтайм-холст');
   d.innerHTML='<div class="k5-cvg"><div><div class="k4-muted">Рисуйте здесь</div><canvas id="k5-ca" width="480" height="360" aria-label="Холст для рисования"></canvas></div><div><div class="k4-muted">Результат вживую</div><canvas id="k5-cb" width="480" height="360" aria-label="Результат"></canvas></div></div>'+
   '<div class="k5-cvt"><input type="color" id="k5-cc" value="#e9b465" aria-label="Цвет" class="k4-in"><input type="range" id="k5-cs" min="2" max="40" value="8" aria-label="Толщина" class="k4-in"><select id="k5-cf" class="k4-in" aria-label="Эффект"><option value="neon">Неон</option><option value="blur">Мягкий</option><option value="invert">Инверсия</option><option value="mono">Моно</option></select><label class="k4-btn"><input type="checkbox" id="k5-cm"> Зеркало</label><button class="k4-btn" type="button" id="k5-cx">Очистить</button><button class="k4-btn pri" type="button" id="k5-cg">Доработай</button></div><div class="k4-out" id="k5-co"></div>';
   A=d.querySelector('#k5-ca');B=d.querySelector('#k5-cb');a=A.getContext('2d');b=B.getContext('2d');a.lineCap='round';a.lineJoin='round';
   A.addEventListener('pointerdown',function(e){draw=true;last=pos(e);A.setPointerCapture(e.pointerId);e.preventDefault()});
   A.addEventListener('pointermove',function(e){if(!draw)return;const p=pos(e);a.strokeStyle=d.querySelector('#k5-cc').value;a.lineWidth=+d.querySelector('#k5-cs').value;a.beginPath();a.moveTo(last[0],last[1]);a.lineTo(p[0],p[1]);a.stroke();last=p;sched()});
   ['pointerup','pointercancel'].forEach(function(n){A.addEventListener(n,function(){draw=false})});
   d.querySelector('#k5-cf').addEventListener('change',sched);d.querySelector('#k5-cm').addEventListener('change',sched);
   d.querySelector('#k5-cx').addEventListener('click',function(){a.clearRect(0,0,A.width,A.height);sched()});
   d.querySelector('#k5-cg').addEventListener('click',function(){const s=stats();
    K4.ask('Я рисую на холсте. Закрашено '+s.cover+'% площади, основные цвета: '+(s.cols.join(', ')||'нет')+', эффект «'+d.querySelector('#k5-cf').selectedOptions[0].textContent+'». Предложи 3 коротких идеи, как доработать рисунок.',d.querySelector('#k5-co'))});
   render()} d.show()}
 K4.ready(function(){K4.fab('k5-cv-b','Реалтайм-холст','brush',open)});
 window.K5canvas={stats:function(){return stats()}};
})();
K5EOF
cat > nox-k5-canvas.css <<'K5EOF'
.k5-cvg{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.k5-cvg canvas{width:100%;height:auto;aspect-ratio:4/3;border-radius:12px;background:#111;border:1px solid rgba(255,255,255,.15);touch-action:none;display:block}
.k5-cvt{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px;align-items:center}
.k5-cvt input[type=color]{width:44px;padding:2px}.k5-cvt input[type=range]{min-width:110px;flex:1;padding:0}
.k5-cvt label.k4-btn input{width:20px;height:20px;margin-right:6px}
@media(max-width:600px){.k5-cvg{grid-template-columns:1fr}}
K5EOF
cat > nox-k5-gaze.js <<'K5EOF'
/* K5 №77 (photo): контент следует за курсором/наклоном: холсты и превью поворачиваются к пользователю. Включается кнопкой «Следи за мной». */
(function(){
 let on=false,raf=0,px=0,py=0;
 function targets(){ const s=[].slice.call(document.querySelectorAll('#page .ps-ed,#page img,#page canvas')).filter(function(e){const r=e.getBoundingClientRect();return r.width>=120&&r.height>=80&&!e.closest('#k4-fab')&&!e.closest('.k4-dlg')});
  return s.filter(function(e){return !s.some(function(o){return o!==e&&o.contains(e)})}).slice(0,6)}
 function apply(){ raf=0; targets().forEach(function(e){const r=e.getBoundingClientRect(),cx=r.left+r.width/2,cy=r.top+r.height/2,dx=Math.max(-1,Math.min(1,(px-cx)/innerWidth*2)),dy=Math.max(-1,Math.min(1,(py-cy)/innerHeight*2));
   e.classList.add('k5-gz');e.style.transform='perspective(900px) rotateY('+(dx*9).toFixed(2)+'deg) rotateX('+(-dy*7).toFixed(2)+'deg)'})}
 function mv(x,y){px=x;py=y;if(on&&!raf)raf=requestAnimationFrame(apply)}
 function set(v,btn){ on=v;btn.setAttribute('aria-pressed',v);btn.querySelector('span')&&(btn.querySelector('span').textContent=v?'Слежу за вами':'Следи за мной');
  if(v){mv(px||innerWidth/2,py||innerHeight/2)}else targets().concat([].slice.call(document.querySelectorAll('.k5-gz'))).forEach(function(e){e.style.transform='';e.classList.remove('k5-gz')})}
 K4.ready(function(){ const btn=K4.fab('k5-gz-b','Следи за мной','eye',function(){set(!on,this)});if(!btn)return;
  btn.setAttribute('aria-pressed','false');
  addEventListener('pointermove',function(e){mv(e.clientX,e.clientY)},{passive:true});
  addEventListener('deviceorientation',function(e){if(e.gamma!=null)mv(innerWidth/2+e.gamma*innerWidth/60,innerHeight/2+(e.beta||0)*innerHeight/90)},{passive:true});
  window.K5gaze={set:function(v){set(v,btn)},on:function(){return on}}});
})();
K5EOF
cat > nox-k5-gaze.css <<'K5EOF'
.k5-gz{transition:transform .12s ease-out;will-change:transform;transform-style:preserve-3d}
#k5-gz-b[aria-pressed=true]{background:rgba(233,180,101,.4);border-color:#e9b465}
@media(prefers-reduced-motion:reduce){.k5-gz{transition:none}}
K5EOF
cat > nox-k5-dj.js <<'K5EOF'
/* K5 №79 (music): Daily DJ: ИИ-голос представляет подборку (K4.ask -> speechSynthesis) */
(function(){
 let d,rate=1;
 function say(t){ if(!window.speechSynthesis)return false; speechSynthesis.cancel(); const u=new SpeechSynthesisUtterance(t);u.lang='ru-RU';u.rate=rate;speechSynthesis.speak(u);return true}
 function open(){ if(!d){d=K4.modal('k5-dj-d','Daily DJ');
   const items=[].map.call(document.querySelectorAll('#mLst li,#mLst .item,#mLst a'),function(x){return x.textContent.trim()}).filter(Boolean).slice(0,8).join('\n');
   d.innerHTML='<label class="k4-muted" for="k5-dt">Подборка (по треку в строке)</label><textarea id="k5-dt" class="k4-in" rows="5" style="width:100%;padding:10px" placeholder="Исполнитель — трек">'+K4.esc(items)+'</textarea>'+
   '<div class="k5-dr"><label class="k4-muted" for="k5-dv">Темп речи</label><input id="k5-dv" class="k4-in" type="range" min="0.7" max="1.4" step="0.1" value="1"></div>'+
   '<div class="k5-dr"><button class="k4-btn pri" type="button" id="k5-dg">Представить подборку</button><button class="k4-btn" type="button" id="k5-dp">Повторить</button><button class="k4-btn" type="button" id="k5-ds">Стоп</button></div><div class="k4-out" id="k5-do"></div>';
   const o=d.querySelector('#k5-do');
   d.querySelector('#k5-dv').addEventListener('input',function(e){rate=+e.target.value});
   d.querySelector('#k5-dg').addEventListener('click',async function(){const l=d.querySelector('#k5-dt').value.trim().split('\n').filter(Boolean).slice(0,10);
    if(!l.length){o.textContent='Добавьте хотя бы один трек.';return}
    const t=await K4.ask('Ты ди-джей NOX на радио. Тепло и живо представь подборку, 4-5 коротких фраз, без списков, по-русски. Треки: '+l.join('; '),o);
    if(t&&!say(t))o.textContent+='\n(озвучка недоступна в этом браузере)'});
   d.querySelector('#k5-dp').addEventListener('click',function(){if(o.textContent&&!say(o.textContent))o.textContent+='\n(озвучка недоступна)'});
   d.querySelector('#k5-ds').addEventListener('click',function(){if(window.speechSynthesis)speechSynthesis.cancel()});
   d.addEventListener('sl-after-hide',function(e){if(e.target===d&&window.speechSynthesis)speechSynthesis.cancel()})} d.show()}
 K4.ready(function(){K4.fab('k5-dj-b','Daily DJ','disc',open)});
})();
K5EOF
cat > nox-k5-dj.css <<'K5EOF'
.k5-dr{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px;align-items:center}
K5EOF
cat > nox-k5-wrapped.js <<'K5EOF'
/* K5 №80 (growth): Wrapped: итоги месяца как сториз; свайп/стрелки (embla-carousel), конфетти (canvas-confetti), итог ИИ через K4.ask */
(function(){
 let d,api=null,idx=0,aiDone=false;
 function stats(){ const t=K4.tasks(),ym=K4.ymd(new Date()).slice(0,7),done=t.filter(function(x){return x.col==='done'}),days={};
  t.forEach(function(x){if(x.due&&x.due.slice(0,7)===ym)days[x.due]=1});
  return{all:t.length,done:done.length,open:t.length-done.length,days:Object.keys(days).length,top:t.filter(function(x){return x.col!=='done'}).slice(0,3).map(function(x){return x.title})}}
 function go(n){ if(api){api.scrollTo(n)}else{const v=d.querySelector('.k5-wv');v.scrollTo({left:n*v.clientWidth,behavior:'smooth'})} }
 function sel(n){idx=n;const s=d.querySelectorAll('.k5-ws');d.querySelector('#k5-wi').textContent=(n+1)+' / '+s.length;
  if(n===s.length-1&&!aiDone){aiDone=true;const st=stats();K4.ask('Подведи итог месяца в 3 коротких предложениях с тёплой интонацией. Задач всего '+st.all+', выполнено '+st.done+', активных дней '+st.days+'.',d.querySelector('#k5-wo'));confetti()}}
 function confetti(){ const c=K4.glob(window.NOX_canvas_confetti);if(typeof c==='function')try{c({particleCount:120,spread:80,origin:{y:.7}})}catch(e){}}
 async function open(){ if(!d){d=K4.modal('k5-wr-d','Итоги месяца');const st=stats();
   d.innerHTML='<div class="k5-wv"><div class="k5-wc">'+
   '<div class="k5-ws"><small>Задачи</small><b>'+st.done+'</b><span>выполнено из '+st.all+'</span></div>'+
   '<div class="k5-ws"><small>Ритм</small><b>'+st.days+'</b><span>дней с делами в этом месяце</span></div>'+
   '<div class="k5-ws"><small>В работе</small><b>'+st.open+'</b><span>'+K4.esc(st.top.join(' · ')||'всё чисто')+'</span></div>'+
   '<div class="k5-ws"><small>Слово NOX</small><div class="k4-out" id="k5-wo">Откройте этот слайд, чтобы получить итог</div></div></div></div>'+
   '<div class="k5-wn"><button class="k4-btn" type="button" id="k5-wp">Назад</button><span id="k5-wi" class="k4-muted">1 / 4</span><button class="k4-btn pri" type="button" id="k5-wx">Дальше</button></div>';
   d.querySelector('#k5-wp').addEventListener('click',function(){go(Math.max(0,idx-1))});
   d.querySelector('#k5-wx').addEventListener('click',function(){go(Math.min(3,idx+1))});
   d.addEventListener('keydown',function(e){if(e.key==='ArrowRight')go(Math.min(3,idx+1));if(e.key==='ArrowLeft')go(Math.max(0,idx-1))});
   const v=d.querySelector('.k5-wv');v.addEventListener('scroll',function(){if(!api)sel(Math.round(v.scrollLeft/Math.max(1,v.clientWidth)))},{passive:true});
   await K4.load('./vendor/embla-carousel/embla-carousel.iife.js');await K4.load('./vendor/canvas-confetti/canvas-confetti.iife.js');
   const E=K4.glob(window.NOX_embla_carousel);d.addEventListener('sl-after-show',function(){ if(typeof E==='function'&&!api){try{api=E(v,{loop:false});api.on('select',function(){sel(api.selectedScrollSnap())});v.classList.add('k5-em')}catch(e){api=null}} else if(api)api.reInit()})}
  d.show()}
 K4.ready(function(){K4.fab('k5-wr-b','Итоги месяца','gift',open)});
 window.K5wrapped={idx:function(){return idx}};
})();
K5EOF
cat > nox-k5-wrapped.css <<'K5EOF'
.k5-wv{overflow-x:auto;scroll-snap-type:x mandatory;border-radius:16px}
.k5-wv.k5-em{overflow:hidden;scroll-snap-type:none}
.k5-wc{display:flex}
.k5-ws{flex:0 0 100%;min-height:260px;box-sizing:border-box;scroll-snap-align:start;padding:24px;display:flex;flex-direction:column;justify-content:center;gap:8px;background:linear-gradient(160deg,rgba(233,180,101,.28),rgba(120,40,60,.35));border-radius:16px;color:#fff}
.k5-ws small{font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:#f1d7a8}
.k5-ws b{font-size:72px;font-weight:300;line-height:1}
.k5-ws span{font-size:14px}
.k5-wn{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-top:12px}
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
add index pulse
grep -q "K5: №75 " qa/rework/index.fixed 2>/dev/null || echo "K5: №75 пульс дня" >> qa/rework/index.fixed
add studio canvas
grep -q "K5: №76 " qa/rework/studio.fixed 2>/dev/null || echo "K5: №76 реалтайм-холст" >> qa/rework/studio.fixed
add photo gaze
grep -q "K5: №77 " qa/rework/photo.fixed 2>/dev/null || echo "K5: №77 следи за мной" >> qa/rework/photo.fixed
add music dj
grep -q "K5: №79 " qa/rework/music.fixed 2>/dev/null || echo "K5: №79 Daily DJ" >> qa/rework/music.fixed
add growth wrapped
grep -q "K5: №80 " qa/rework/growth.fixed 2>/dev/null || echo "K5: №80 итоги месяца" >> qa/rework/growth.fixed
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python
timeout 250 $PY /tmp/k2_qa.py index studio photo music growth 2>&1 | tail -12
$PY - <<'QAEOF'
import asyncio,json
from playwright.async_api import async_playwright
C=[["index", "pulse", "(async()=>{const b=document.getElementById('k5-pb');if(!b)return 'NO';b.click();await new Promise(r=>setTimeout(r,2500));return JSON.stringify({open:!document.getElementById('k5-pp').hidden,facts:document.getElementById('k5-pf').textContent.length>10,out:document.getElementById('k5-po').textContent.length>0,h:b.offsetHeight})})()"], ["studio", "canvas", "(async()=>{const f=document.getElementById('k5-cv-b');if(!f)return 'NO';f.click();await new Promise(r=>setTimeout(r,500));const A=document.getElementById('k5-ca');A.scrollIntoView();const r=A.getBoundingClientRect();return JSON.stringify({x:r.x,y:r.y,w:r.width,h:r.height})})()"], ["photo", "gaze", "(async()=>{const f=document.getElementById('k5-gz-b');if(!f)return 'NO';f.click();dispatchEvent(new PointerEvent('pointermove',{clientX:50,clientY:50}));await new Promise(r=>setTimeout(r,500));const t=[...document.querySelectorAll('.k5-gz')];return JSON.stringify({pressed:f.getAttribute('aria-pressed'),n:t.length,tr:t[0]&&t[0].style.transform.slice(0,50),h:f.offsetHeight})})()"], ["music", "dj", "(async()=>{const f=document.getElementById('k5-dj-b');if(!f)return 'NO';f.click();await new Promise(r=>setTimeout(r,400));document.getElementById('k5-dt').value='Muse — Starlight\\nQueen — Radio Ga Ga';document.getElementById('k5-dg').click();await new Promise(r=>setTimeout(r,2500));return JSON.stringify({out:document.getElementById('k5-do').textContent.slice(0,60),h:document.getElementById('k5-dg').offsetHeight})})()"], ["growth", "wrapped", "(async()=>{const f=document.getElementById('k5-wr-b');if(!f)return 'NO';f.click();await new Promise(r=>setTimeout(r,1500));const s=document.querySelectorAll('.k5-ws').length;document.getElementById('k5-wx').click();await new Promise(r=>setTimeout(r,1200));return JSON.stringify({slides:s,idx:document.getElementById('k5-wi').textContent,h:document.getElementById('k5-wx').offsetHeight})})()"]]
async def m():
  async with async_playwright() as p:
    b=await p.chromium.launch(args=['--use-gl=swiftshader','--enable-unsafe-swiftshader'])
    for w,h in((1440,900),(390,844)):
      for u,f,js in C:
        pg=await b.new_page(viewport={'width':w,'height':h});errs=[];pg.on('pageerror',lambda e:errs.append(str(e)[:120]))
        try:
          await pg.goto('http://127.0.0.1:8091/web/'+u+'.html',wait_until='load',timeout=25000);await pg.wait_for_timeout(3500)
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
