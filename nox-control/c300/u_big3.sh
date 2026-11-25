echo "C300: u_big3"
S=/workspace/nox/web/site; cd $S; TS=$(date +%s)
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python
echo "== 1 CSS belt (mobile fonts)"
cp nox-m-mobile.css nox-m-mobile.css.bak_u_$TS
grep -q U_BELT nox-m-mobile.css || printf '\n/* U_BELT */\n@media (max-width:768px){.mono,small,dt,dd,figcaption,caption,sub,sup{font-size:14px !important}}\n' >> nox-m-mobile.css
sed -i -E 's#nox-m-mobile\.css\?v=[A-Za-z0-9_]+#nox-m-mobile.css?v=u1#' *.html
echo "== 2 minichat finance/mail click diag"
cat > /tmp/u_d.py <<'PEOF'
import asyncio
from playwright.async_api import async_playwright
async def m():
  async with async_playwright() as p:
    b=await p.chromium.launch()
    for pg in ('finance','mail'):
      c=await b.new_page(viewport={'width':1440,'height':900})
      await c.goto('http://127.0.0.1:8091/web/%s.html'%pg,wait_until='domcontentloaded');await c.wait_for_timeout(3500)
      r=await c.evaluate("""()=>{const f=document.querySelector('.nmc-fab');if(!f)return 'nofab';const b=f.getBoundingClientRect(),s=getComputedStyle(f);const x=b.left+b.width/2,y=b.top+b.height/2;const t=document.elementFromPoint(x,y);return {rect:[b.left|0,b.top|0,b.width|0,b.height|0],vis:s.visibility+'/'+s.display+'/'+s.opacity+'/'+s.pointerEvents,top:t?(t.tagName+'#'+t.id+'.'+String(t.className).slice(0,40)):null,own:t===f||f.contains(t)}}""")
      print('DIAG',pg,r)
      try:
        await c.evaluate("document.querySelector('.nmc-fab').click()");await c.wait_for_timeout(900)
        print('DIAG js-click ->',await c.evaluate("[...document.querySelectorAll('[class*=nmc],[id*=nmc]')].filter(x=>x.offsetParent||getComputedStyle(x).position==='fixed').map(x=>x.id+'.'+String(x.className).slice(0,25)).slice(0,8)"))
      except Exception as e: print('DIAG err',str(e)[:80])
    await b.close()
asyncio.run(m())
PEOF
timeout 90 $PY /tmp/u_d.py
echo "== 3 dead-button handlers"
for k in s6sl s6fAdd tvBtn s2x; do echo "-- $k"; grep -l "$k" *.js *.html 2>/dev/null | head -4 | tr '\n' ' '; echo; grep -ho ".\{0,90\}$k.\{0,120\}" *.js 2>/dev/null | head -2; done
echo "== 4 audit progress"; cut -c1-330 /tmp/u_aud.out | sed -n 8,80p
echo "u_big3 done"
