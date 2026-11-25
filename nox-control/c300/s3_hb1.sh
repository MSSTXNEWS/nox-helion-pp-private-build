PY=/workspace/nox/venv/bin/python
echo "== HB1"
cat > /tmp/s3_hb1.py <<'P'
from playwright.sync_api import sync_playwright
SNAP="""()=>{const vis=[...document.querySelectorAll('body *')].filter(e=>{const s=getComputedStyle(e);const r=e.getBoundingClientRect();return r.width>30&&r.height>30&&s.visibility!='hidden'&&s.display!='none'&&+s.opacity>0.05&&(s.position=='fixed'||s.position=='absolute')}).length;const n=document.querySelector('ninja-keys');return {fixedAbs:vis,ninja:!!(n&&n.visible),url:location.pathname.split('/').pop(),dlg:document.querySelectorAll('[role=dialog]:not([hidden]),dialog[open],.nxdp[style*=block],[class*=pop][class*=open],[aria-expanded=true]').length,html:document.documentElement.className.length+document.body.className.length}}"""
with sync_playwright() as p:
    b=p.chromium.launch()
    for pgn in ('news','photo','index'):
        for sel in ('#tbSearch','#tbFav','#tbBell','#tbNotes'):
            ctx=b.new_context(viewport={'width':1440,'height':900},service_workers='block'); pg=ctx.new_page(); errs=[]; pg.on('pageerror',lambda e: errs.append(str(e)[:80])); reqs=[]; pg.on('request',lambda r: reqs.append(r.url.split('/')[-1][:20]) if '/api/' in r.url else None)
            pg.goto('http://localhost:8091/web/%s.html'%pgn,wait_until='load'); pg.wait_for_timeout(3500)
            vis=pg.evaluate("(s)=>{const e=document.querySelector(s);if(!e)return 'MISSING';const r=e.getBoundingClientRect(),c=getComputedStyle(e);return [c.display,c.visibility,Math.round(r.width)+'x'+Math.round(r.height),e.getAttribute('aria-label'),e.hasAttribute('hidden')]}",sel)
            before=pg.evaluate(SNAP)
            try: pg.click(sel,timeout=3000); pg.wait_for_timeout(900); after=pg.evaluate(SNAP)
            except Exception as e: after='CLICK ERR '+str(e)[:60]
            print('R:',pgn,sel,vis,'before',before,'after',after,errs[:1]); ctx.close()
    # pult buttons and FAB geometry
    ctx=b.new_context(viewport={'width':1440,'height':900},service_workers='block'); pg=ctx.new_page(); pg.goto('http://localhost:8091/web/news.html',wait_until='load'); pg.wait_for_timeout(3500)
    print('R: geo', pg.evaluate("()=>{const d=document.getElementById('nxdock').getBoundingClientRect().top;return [...document.querySelectorAll('#nxpult,.nxpu-tog,.nmc-fab,#nxmPill,#nxnavx,#nxdTools .nxd-r')].map(e=>{const r=e.getBoundingClientRect();return (e.id||e.className.toString().slice(0,12))+' top'+Math.round(r.top)+' bottom'+Math.round(r.bottom)+' dockTop'+Math.round(d)+' vis'+(getComputedStyle(e).display!='none')}) }"))
    b.close()
P
timeout 250 $PY -I /tmp/s3_hb1.py 2>&1 | cut -c1-420
