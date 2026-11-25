echo "C300: k5_a_1b"
S=/workspace/nox/web/site; cd $S
TS=$(date +%s)
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
add studio canvas
grep -q "K5: №76 " qa/rework/studio.fixed 2>/dev/null || echo "K5: №76 реалтайм-холст" >> qa/rework/studio.fixed
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python
timeout 250 $PY /tmp/k2_qa.py studio 2>&1 | tail -12
$PY - <<'QAEOF'
import asyncio,json
from playwright.async_api import async_playwright
C=[["studio", "canvas", "(async()=>{const f=document.getElementById('k5-cv-b');if(!f)return 'NO';f.click();await new Promise(r=>setTimeout(r,500));const A=document.getElementById('k5-ca');A.scrollIntoView();const r=A.getBoundingClientRect();return JSON.stringify({x:r.x,y:r.y,w:r.width,h:r.height})})()"]]
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
