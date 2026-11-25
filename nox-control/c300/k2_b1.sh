echo "C300: k2_b1"
S=/workspace/nox/web/site; cd $S
TS=$(date +%s)
cat > nox-k2-softgaze.css <<'EOF'
/* K2 №10: мягкий взгляд — соседние карточки отступают и тускнеют (visionOS) */
@media (hover:hover) and (prefers-reduced-motion:no-preference){
 :has(> .card:hover) > .card:not(:hover){opacity:.74;filter:saturate(.8);transform:scale(.992);transition:opacity .35s,transform .35s,filter .35s}
 .card{transition:opacity .35s,transform .35s,filter .35s}
}
EOF
cat > nox-k2-tilt.css <<'EOF'
/* K2: плавающий наклон карточки к курсору */
.card.k2-tilt{transform:perspective(900px) rotateX(var(--k2rx,0deg)) rotateY(var(--k2ry,0deg)) translateZ(0);transition:transform .18s ease-out}
EOF
cat > nox-k2-tilt.js <<'EOF'
/* K2: наклон карточек visionOS-стиль; не трогает карточки с графиками/таблицами */
(function(){
 if(matchMedia('(prefers-reduced-motion:reduce)').matches||!matchMedia('(hover:hover)').matches)return;
 let cur=null;
 document.addEventListener('pointermove',function(e){
  const c=e.target.closest&&e.target.closest('.card');
  if(cur&&cur!==c){cur.style.removeProperty('--k2rx');cur.style.removeProperty('--k2ry');cur.classList.remove('k2-tilt');cur=null}
  if(!c||c.querySelector('canvas,table,textarea,input,.chart,iframe'))return;
  cur=c;c.classList.add('k2-tilt');
  const r=c.getBoundingClientRect(),x=(e.clientX-r.left)/r.width-.5,y=(e.clientY-r.top)/r.height-.5;
  c.style.setProperty('--k2ry',(x*5).toFixed(2)+'deg');c.style.setProperty('--k2rx',(-y*5).toFixed(2)+'deg');
 },{passive:true});
 document.addEventListener('pointerleave',function(){if(cur){cur.style.removeProperty('--k2rx');cur.style.removeProperty('--k2ry');cur=null}},true);
})();
EOF
cat > nox-k2-shake.css <<'EOF'
@keyframes k2shake{0%,100%{transform:translateX(0)}20%{transform:translateX(-7px)}40%{transform:translateX(6px)}60%{transform:translateX(-4px)}80%{transform:translateX(3px)}}
.k2-shake{animation:k2shake .38s ease-in-out;outline:2px solid #e9b465;outline-offset:2px}
@media (prefers-reduced-motion:reduce){.k2-shake{animation:none}}
EOF
cat > nox-k2-shake.js <<'EOF'
/* K2: пустая отправка в чат — поле встряхивается (Raycast 2.12) */
(function(){
 function go(){const b=document.getElementById('btnSend'),i=document.getElementById('input'),c=document.getElementById('composer')||(i&&i.parentElement);
  if(!b||!i||!c)return;
  b.addEventListener('click',function(){if(!(i.value||i.textContent||'').trim()){c.classList.remove('k2-shake');void c.offsetWidth;c.classList.add('k2-shake');setTimeout(function(){c.classList.remove('k2-shake')},450)}},true);}
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',go);else go();
})();
EOF
cat > nox-k2-selask.css <<'EOF'
#k2-selask{position:fixed;z-index:1150;display:none;min-height:44px;min-width:44px}
#k2-selask.on{display:block}
#k2-selask sl-button::part(base){min-height:44px;font-size:14px}
#k2-toast{position:fixed;left:50%;bottom:calc(var(--ds-dock-h,64px) + 24px);transform:translateX(-50%);z-index:1200;padding:12px 18px;border-radius:14px;font-size:14px;color:#efe6df;background:rgba(16,13,13,.86);border:1px solid rgba(255,255,255,.16);backdrop-filter:blur(14px)}
EOF
cat > nox-k2-selask.js <<'EOF'
/* K2: «Спросить NOX» по выделению текста (Acrobat AI) + Ctrl/Cmd+J: отправить выделение в чат. Связь: NOXcmd chat.send -> /api/chat */
(function(){
 let box=null,txt='';
 function toast(m){const t=document.createElement('div');t.id='k2-toast';t.textContent=m;document.body.appendChild(t);setTimeout(function(){t.remove()},2400)}
 function ask(t,pre){t=(t||'').trim().slice(0,6000);if(!t){toast('Выделите текст');return}
  const msg=(pre||'Объясни коротко: ')+t;
  if(typeof window.NOXcmd==='function'){window.NOXcmd('chat.send',{message:msg}).then(function(){toast('Отправлено в чат NOX')}).catch(function(){toast('Чат недоступен')})}else toast('Команды недоступны');
  hide()}
 function hide(){if(box)box.classList.remove('on')}
 function mk(){if(box)return box;box=document.createElement('div');box.id='k2-selask';
  if(window.customElements&&customElements.get('sl-button')){box.innerHTML='<sl-button variant="primary" size="large" pill>Спросить NOX</sl-button>'}
  else{box.innerHTML='<button type="button" class="btn" style="min-height:44px;min-width:44px;font-size:14px">Спросить NOX</button>'}
  box.addEventListener('mousedown',function(e){e.preventDefault()});
  box.addEventListener('click',function(){ask(txt)});document.body.appendChild(box);return box}
 document.addEventListener('mouseup',function(e){
  if(e.target.closest&&e.target.closest('#k2-selask'))return;
  setTimeout(function(){const s=getSelection();const t=s?String(s).trim():'';
   if(t.length<12){hide();return}
   const a=s.anchorNode&&(s.anchorNode.nodeType===1?s.anchorNode:s.anchorNode.parentElement);
   if(a&&a.closest&&a.closest('input,textarea,[contenteditable="true"],#input'))return;
   txt=t;const r=s.getRangeAt(0).getBoundingClientRect(),b=mk();b.classList.add('on');
   b.style.left=Math.max(8,Math.min(innerWidth-170,r.left+r.width/2-70))+'px';b.style.top=Math.max(8,r.top-54)+'px'},10)});
 document.addEventListener('keydown',function(e){
  if((e.ctrlKey||e.metaKey)&&!e.shiftKey&&!e.altKey&&(e.key==='j'||e.key==='J'||e.code==='KeyJ')){
   e.preventDefault();ask(String(getSelection()||'')||document.title,'Расскажи про: ')}
  if(e.key==='Escape')hide()});
 document.addEventListener('scroll',hide,{passive:true,capture:true});
})();
EOF
add(){ # page, tags
 f=$1.html; [ -f $f ] || { echo "no $f"; return; }
 grep -q "nox-k2-$2" $f && { echo "have $f $2"; return; }
 cp $f $f.bak_k2_$TS
 tag=""
 [ -f nox-k2-$2.css ] && tag="$tag<link rel=\"stylesheet\" href=\"./nox-k2-$2.css?v=k2a\">"
 [ -f nox-k2-$2.js ] && tag="$tag<script src=\"./nox-k2-$2.js?v=k2a\" defer></script>"
 python3 - "$f" "$tag" <<'PY'
import sys
f,t=sys.argv[1],sys.argv[2]
s=open(f,encoding='utf-8').read()
i=s.rfind('</body>')
s=s[:i]+t+s[i:] if i>=0 else s+t
open(f,'w',encoding='utf-8').write(s)
PY
 echo "added $2 -> $f"; }
for p in index system growth news memory; do add $p softgaze; done
for p in index growth; do add $p tilt; done
add chat shake
for p in pdf news memory assistant index knowledge; do add $p selask; done
# QA
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python; $PY -c 'import playwright' 2>/dev/null || PY=python3
cat > /tmp/k2_qa.py <<'EOF'
import asyncio,sys
from playwright.async_api import async_playwright
pages=sys.argv[1:]
async def main():
  async with async_playwright() as p:
    b=await p.chromium.launch()
    for w,h in((1440,900),(390,844)):
      for pg in pages:
        c=await b.new_context(viewport={'width':w,'height':h});pgx=await c.new_page();errs=[]
        pgx.on('pageerror',lambda e:errs.append(str(e)[:120]))
        try:
          await pgx.goto('http://127.0.0.1:8080/web/'+pg+'.html',wait_until='load',timeout=25000);await pgx.wait_for_timeout(1500)
        except Exception as e: errs.append('goto '+str(e)[:80])
        k=[e for e in errs if 'k2' in e.lower()]
        print(w,pg,'errs',len(errs),k[:2])
        if pg=='index' and w==1440: await pgx.screenshot(path='/tmp/k2_shot.jpg',type='jpeg',quality=35)
        await c.close()
    await b.close()
asyncio.run(main())
EOF
grep -o "127.0.0.1:[0-9]*" /workspace/nox/web/pkg/server/run_web.sh | head -2
timeout 150 $PY /tmp/k2_qa.py index system growth news memory chat pdf assistant knowledge 2>&1 | tail -25
echo "K2: добавлены фишки №10(soft-gaze), tilt, shake, selask/⌘J" >> qa/rework/index.fixed
exit 0
