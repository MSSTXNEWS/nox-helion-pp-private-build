echo "C300: u_big10"
S=/workspace/nox/web/site; cd $S; TS=$(date +%s); O=/workspace/nox/agent/out
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python
cat > /tmp/u_f5.py <<'PEOF'
import asyncio
from playwright.async_api import async_playwright
CAND={'A':"html:not(#u) body button.nmc-fab{bottom:200px !important}",
'B':"html:not(#u) body sl-button.nai-btn{right:90px !important}",
'C':"html:not(#u) body button.nmc-fab{z-index:900 !important}"}
async def m():
  async with async_playwright() as p:
    b=await p.chromium.launch()
    for k,css in [('none','')]+list(CAND.items()):
      c=await b.new_page(viewport={'width':1440,'height':900})
      await c.goto('http://127.0.0.1:8091/web/finance.html',wait_until='domcontentloaded');await c.wait_for_timeout(4000)
      if css: await c.add_style_tag(content=css);await c.wait_for_timeout(300)
      if k=='none': print('INLINE',await c.evaluate("[document.querySelector('.nmc-fab').getAttribute('style'),document.querySelector('.nai-btn').getAttribute('style')]"))
      try: await c.click('.nmc-fab',timeout=2000);r='ok'
      except Exception: r='ERR'
      print('CAND',k,r,flush=True);await c.close()
    await b.close()
asyncio.run(m())
PEOF
timeout 100 $PY /tmp/u_f5.py | tee /tmp/u_f5.out
W=$(grep "CAND [ABC] ok" /tmp/u_f5.out | head -1 | awk '{print $2}')
echo "winner=$W"
cp nox-unify.css nox-unify.css.bak_u4_$TS
case "$W" in
 A) printf '\n/* U_FABFIX */\n@media (min-width:769px){html:not(#u) body button.nmc-fab{bottom:200px !important}}\n' >> nox-unify.css;;
 B) printf '\n/* U_FABFIX */\n@media (min-width:769px){html:not(#u) body sl-button.nai-btn{right:90px !important}}\n' >> nox-unify.css;;
 C) printf '\n/* U_FABFIX */\n@media (min-width:769px){html:not(#u) body button.nmc-fab{z-index:900 !important}}\n' >> nox-unify.css;;
esac
sed -i -E 's#nox-unify\.css\?v=[A-Za-z0-9_]+#nox-unify.css?v=u4#' *.html
echo "== audit progress"; cat $O/u_qaa_prog.txt 2>/dev/null; ls -la $O | grep u_qaa; tail -3 $O/u_qaa_1.out | cut -c1-300
