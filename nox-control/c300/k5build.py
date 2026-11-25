import sys,json,os
name=sys.argv[1]; feats=sys.argv[2].split(',')  # name:page:num
MAP={'pulse':('index',75),'canvas':('studio',76),'gaze':('photo',77),'dj':('music',79),'wrapped':('growth',80),'xray':('cinema',81),'diff':('assistant',82),'see':('voice',83),'mascot':('chat',84),'motion100':('chat',0)}
LABEL={'pulse':'пульс дня','canvas':'реалтайм-холст','gaze':'следи за мной','dj':'Daily DJ','wrapped':'итоги месяца','xray':'X-Ray','diff':'диф правок ИИ','see':'что это','mascot':'талисман состояний','motion100':'100 анимаций ANM-001..100'}
CHK={
'motion100':"(async()=>{await new Promise(r=>setTimeout(r,1500));const n=NOXMotion.list.length;const el=document.querySelector('#k5-mc svg')||document.body;NOXMotion.state('alarm',el);await new Promise(r=>setTimeout(r,300));const a=el.dataset.anm;NOXMotion.state('joy',el);return JSON.stringify({n,alarm:a,joy:el.dataset.anm,cls:/anm-/.test(el.getAttribute('class')||''),gsap:!!window.gsap,css:[...document.styleSheets].some(s=>(s.href||'').includes('motion100'))})})()",
'pulse':"(async()=>{const b=document.getElementById('k5-pb');if(!b)return 'NO';b.click();await new Promise(r=>setTimeout(r,2500));return JSON.stringify({open:!document.getElementById('k5-pp').hidden,facts:document.getElementById('k5-pf').textContent.length>10,out:document.getElementById('k5-po').textContent.length>0,h:b.offsetHeight})})()",
'canvas':"(async()=>{const f=document.getElementById('k5-cv-b');if(!f)return 'NO';f.click();await new Promise(r=>setTimeout(r,500));const A=document.getElementById('k5-ca');A.scrollIntoView();const r=A.getBoundingClientRect();return JSON.stringify({x:r.x,y:r.y,w:r.width,h:r.height})})()",
'gaze':"(async()=>{const f=document.getElementById('k5-gz-b');if(!f)return 'NO';f.click();dispatchEvent(new PointerEvent('pointermove',{clientX:50,clientY:50}));await new Promise(r=>setTimeout(r,500));const t=[...document.querySelectorAll('.k5-gz')];return JSON.stringify({pressed:f.getAttribute('aria-pressed'),n:t.length,tr:t[0]&&t[0].style.transform.slice(0,50),h:f.offsetHeight})})()",
'dj':"(async()=>{const f=document.getElementById('k5-dj-b');if(!f)return 'NO';f.click();await new Promise(r=>setTimeout(r,400));document.getElementById('k5-dt').value='Muse — Starlight\\nQueen — Radio Ga Ga';document.getElementById('k5-dg').click();await new Promise(r=>setTimeout(r,2500));return JSON.stringify({out:document.getElementById('k5-do').textContent.slice(0,60),h:document.getElementById('k5-dg').offsetHeight})})()",
'wrapped':"(async()=>{const f=document.getElementById('k5-wr-b');if(!f)return 'NO';f.click();await new Promise(r=>setTimeout(r,1500));const s=document.querySelectorAll('.k5-ws').length;document.getElementById('k5-wx').click();await new Promise(r=>setTimeout(r,1200));return JSON.stringify({slides:s,idx:document.getElementById('k5-wi').textContent,h:document.getElementById('k5-wx').offsetHeight})})()",
'xray':"(async()=>{const f=document.getElementById('k5-xr-b');if(!f)return 'NO';f.click();await new Promise(r=>setTimeout(r,400));document.getElementById('k5-xt').value='Тест';document.getElementById('k5-xg').click();await new Promise(r=>setTimeout(r,2500));return JSON.stringify({out:document.getElementById('k5-xo').textContent.slice(0,60),h:document.getElementById('k5-xg').offsetHeight})})()",
'diff':"(async()=>{const f=document.getElementById('k5-df-b');if(!f)return 'NO';f.click();await new Promise(r=>setTimeout(r,400));K5diff.build('a\\nb\\nc','a\\nB\\nc');const h=K5diff.hunks().filter(x=>x.eq===undefined).length;const bt=document.querySelector('#k5-dfv button[data-a=ok]');bt.click();return JSON.stringify({hunks:h,res:K5diff.result(),h:bt.offsetHeight,add:document.querySelectorAll('.k5-dl.add').length,del:document.querySelectorAll('.k5-dl.del').length})})()",
'see':"(async()=>{const f=document.getElementById('k5-se-b');if(!f)return 'NO';f.click();await new Promise(r=>setTimeout(r,400));document.getElementById('k5-st').value='чашка';document.getElementById('k5-sg').click();await new Promise(r=>setTimeout(r,2500));return JSON.stringify({out:document.getElementById('k5-so').textContent.slice(0,60),h:document.getElementById('k5-sg').offsetHeight})})()",
'mascot':"(async()=>{const m=document.getElementById('k5-mc');if(!m)return 'NO';K5mascot.set('think');const a=K5mascot.state();K5mascot.set('speak');return JSON.stringify({a,b:K5mascot.state(),label:m.getAttribute('aria-label'),w:m.offsetWidth,h:m.offsetHeight})})()",
}
o=['echo "C300: %s"'%name,'S=/workspace/nox/web/site; cd $S','TS=$(date +%s)']
for f in feats:
    for ext in('js','css'):
        p='/home/claude/k5src/nox-k5-%s.%s'%(f,ext)
        o.append("cat > nox-k5-%s.%s <<'K5EOF'\n%s\nK5EOF"%(f,ext,open(p).read().rstrip('\n')))
o.append('''add(){ f=$1.html; [ -f $f ] || { echo "no $f"; return; }
 grep -q "nox-k5-$2.js" $f && { echo "have $f $2"; return; }
 cp $f $f.bak_k5_$TS; tag=""
 grep -q "nox-k4-core.js" $f || tag="<script src=\\"./nox-k4-core.js?v=k4a\\" defer></script>"
 tag="$tag<link rel=\\"stylesheet\\" href=\\"./nox-k5-$2.css?v=k5a\\"><script src=\\"./nox-k5-$2.js?v=k5a\\" defer></script>"
 python3 - "$f" "$tag" <<'PY'
import sys
f,t=sys.argv[1],sys.argv[2]
s=open(f,encoding='utf-8').read();i=s.rfind('</body>')
open(f,'w',encoding='utf-8').write(s[:i]+t+s[i:] if i>=0 else s+t)
PY
 echo "added $2 -> $f"; }''')
for f in feats:
    pg,n=MAP[f]
    if f=='motion100':
        o.append('add index motion100\nadd voice motion100\ngrep -q "K5: motion100" qa/rework/index.fixed || echo "K5: motion100 ANM-001..100" >> qa/rework/index.fixed\ngrep -q "K5: motion100" qa/rework/voice.fixed || echo "K5: motion100 ANM-001..100" >> qa/rework/voice.fixed')
    o.append('add %s %s\ngrep -q "K5: №%d " qa/rework/%s.fixed 2>/dev/null || echo "K5: №%d %s" >> qa/rework/%s.fixed'%(pg,f,n,pg,n,LABEL[f],pg))
pages=' '.join(MAP[f][0] for f in feats)+(' index voice' if 'motion100' in feats else '')
o.append('export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python\ntimeout 250 $PY /tmp/k2_qa.py %s 2>&1 | tail -12'%pages)
C=[[MAP[f][0],f,CHK[f]] for f in feats]
py='''import asyncio,json
from playwright.async_api import async_playwright
C=%s
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
'''%json.dumps(C,ensure_ascii=False)
o.append("$PY - <<'QAEOF'\n"+py+"QAEOF")
d='/home/claude/stage_'+name;os.makedirs(d,exist_ok=True)
open(d+'/%s.sh'%name,'w').write('\n'.join(o)+'\n')
