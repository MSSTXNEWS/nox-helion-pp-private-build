echo "C300: u_dep_pad4"
S=/workspace/nox/web/site; export S; cd $S; TS=$(date +%s)
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python; export PATH=/workspace/nox/tools/node/bin:$PATH
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles
curl -fsSL --retry 5 --retry-delay 4 --retry-all-errors $R/u_pad/nox-u-pad.js -o /tmp/nox-u-pad.js || { echo FAIL; exit 0; }
node --check /tmp/nox-u-pad.js || { echo SYNTAX; exit 0; }
cp nox-u-pad.js nox-u-pad.js.bak_u4_$TS; cp /tmp/nox-u-pad.js nox-u-pad.js
sed -i 's#nox-u-pad.js?v=[a-z0-9]*#nox-u-pad.js?v=p4#' *.html
cat > /tmp/u_pad2.py <<'PEOF'
import asyncio,json,urllib.request,os
S=os.environ['S']
from playwright.async_api import async_playwright
B='http://127.0.0.1:8091'
JS="""()=>{const p=document.getElementById('u-pad').getBoundingClientRect();const out=[];document.querySelectorAll('body *').forEach(e=>{if(e.closest('#u-pad')||e.id==='u-tab'||e.id==='u-pop')return;const cs=getComputedStyle(e);if(cs.position!=='fixed')return;if(cs.display==='none'||cs.visibility==='hidden'||+cs.opacity===0)return;const r=e.getBoundingClientRect();if(r.width<8||r.height<8)return;const ix=Math.min(r.right,p.right)-Math.max(r.left,p.left),iy=Math.min(r.bottom,p.bottom)-Math.max(r.top,p.top);if(ix>4&&iy>4)out.push((e.tagName+'#'+e.id+'.'+String(e.className).slice(0,28)+' '+[r.left|0,r.top|0,r.width|0,r.height|0]).slice(0,110))});return [[p.left|0,p.top|0,p.width|0,p.height|0],out.slice(0,12)]}"""
async def m():
  async with async_playwright() as p:
    b=await p.chromium.launch()
    for pg in('index','chat'):
      for w,h in((1440,900),(390,844)):
        c=await b.new_page(viewport={'width':w,'height':h});errs=[];c.on('pageerror',lambda e:errs.append(str(e)[:90]))
        await c.goto(B+'/web/%s.html'%pg+('?home=1' if w<500 and pg=='index' else ''),wait_until='domcontentloaded');await c.wait_for_timeout(5000)
        await c.evaluate("window.NOXNote&&NOXNote.open()");await c.wait_for_timeout(700)
        print('OVL',pg,w,json.dumps(await c.evaluate(JS),ensure_ascii=False),'ERRS',errs[:1],flush=True);await c.close()
    # mobile swipe + button
    ctx=await b.new_context(viewport={'width':390,'height':844},has_touch=True,is_mobile=True);c=await ctx.new_page()
    await c.goto(B+'/web/index.html?home=1',wait_until='domcontentloaded');await c.wait_for_timeout(5000)
    s=await ctx.new_cdp_session(c)
    await s.send('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[{'x':386,'y':400}]})
    for x in (340,300,250,200):await s.send('Input.dispatchTouchEvent',{'type':'touchMove','touchPoints':[{'x':x,'y':400}]})
    await s.send('Input.dispatchTouchEvent',{'type':'touchEnd','touchPoints':[]});await c.wait_for_timeout(700)
    sw=await c.evaluate("document.getElementById('u-pad').className")
    await c.evaluate("NOXNote.close()");await c.wait_for_timeout(500)
    await c.tap('#u-tab');await c.wait_for_timeout(700)
    print('MOB swipe',sw,'button',await c.evaluate("document.getElementById('u-pad').className"),flush=True)
    await c.screenshot(path=S+'/qa/u_pad_m390.png');await ctx.close()
    # sync + live NOX + board
    c1=await b.new_page(viewport={'width':1440,'height':900});await c1.goto(B+'/web/board.html',wait_until='domcontentloaded');await c1.wait_for_timeout(5000)
    await c1.evaluate("localStorage.removeItem('nox.pad.v1');NOXNote.open()");await c1.wait_for_timeout(500)
    await c1.evaluate("(async()=>{await NOXNote.add('U_QA_PAD живой тест листа',{to:'both'})})()");await c1.wait_for_timeout(4500)
    notes=json.load(urllib.request.urlopen(B+'/api/notes')).get('notes',[])
    print('NOTES',[n['id'] for n in notes if 'pad-' in str(n.get('id')) or 'U_QA_PAD' in n.get('text','')][:5])
    try:
      r=json.load(urllib.request.urlopen(B+'/svc/nox-living/mem/search?q=U_QA_PAD'));print('RECALL',json.dumps(r,ensure_ascii=False)[:200])
    except Exception as e:print('RECALL err',e)
    await c1.reload();await c1.wait_for_timeout(6000)
    print('BOARD',await c1.evaluate("(JSON.parse(localStorage.getItem('nox.s2.board')||'{}').elements||[]).filter(e=>/U_QA_PAD/.test(e.text||'')).length"),'canvas',await c1.evaluate("document.querySelectorAll('canvas').length"))
    await c1.screenshot(path=S+'/qa/u_pad_board.png')
    c2=await b.new_page(viewport={'width':1440,'height':900});await c2.goto(B+'/web/settings.html',wait_until='domcontentloaded');await c2.wait_for_timeout(4000)
    await c2.evaluate("localStorage.removeItem('nox.pad.v1')");await c2.reload();await c2.wait_for_timeout(5000)
    print('SYNC pulled',await c2.evaluate("JSON.stringify(NOXNote.sheets()).includes('U_QA_PAD')"),flush=True)
    # cleanup test notes
    n=json.load(urllib.request.urlopen(B+'/api/notes')).get('notes',[]);n=[x for x in n if 'U_QA_PAD' not in x.get('text','')]
    urllib.request.urlopen(urllib.request.Request(B+'/api/notes',json.dumps({'notes':n}).encode(),{'Content-Type':'application/json'}))
    await b.close()
asyncio.run(m())
PEOF
timeout 170 $PY /tmp/u_pad2.py 2>&1 | tee /tmp/u_pad2.out | cut -c1-600
grep -E "^(OVL|MOB)" /tmp/u_pad2.out | grep -q "ERRS \['" && { cp nox-u-pad.js.bak_u4_$TS nox-u-pad.js; sed -i 's#nox-u-pad.js?v=p4#nox-u-pad.js?v=p3#' *.html; echo ROLLBACK; } || echo QA_CLEAN
echo done
