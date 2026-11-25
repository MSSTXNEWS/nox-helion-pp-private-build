PY=/workspace/nox/venv/bin/python
echo "== CT"
cat > /tmp/s3_cu2.py <<'P'
import json,time
from playwright.sync_api import sync_playwright
n=json.load(open('/workspace/nox/web/site/nav.json',encoding='utf-8'))
items=[(g['group'],i['file'],i['name']) for g in n['groups'] for i in g['items']][12:24]
cells_js="()=>[...document.querySelectorAll('#nxdock .nxd-cells a')].map(a=>({t:a.textContent.trim(),h:a.getAttribute('href')}))"
with sync_playwright() as p:
    b=p.chromium.launch()
    for grp,f,name in items:
        ctx=b.new_context(viewport={'width':1440,'height':900},service_workers='block'); pg=ctx.new_page(); errs=[]; pg.on('pageerror',lambda e: errs.append(str(e)[:80]))
        res='?'
        try:
            pg.goto('http://localhost:8091/web/index.html',wait_until='load'); pg.wait_for_timeout(2500)
            cells=pg.evaluate(cells_js); idx=[i for i,c in enumerate(cells) if c['t'].upper().startswith(grp.upper()[:6])]
            if grp=='СИСТЕМА':
                sel='.tb a[href$="%s"], .tb [data-k] ' % f
                loc=pg.locator('.tb a[href$="%s"]' % f)
                if loc.count()==0: res='FAIL нет ссылки в шапке'
                else: loc.first.click(); pg.wait_for_url(lambda u: u.split('?')[0].endswith(f),timeout=9000); pg.wait_for_timeout(800); res='OK' if pg.url.endswith(f) else 'FAIL url '+pg.url[-30:]
            elif not idx: res='FAIL нет ячейки дока'
            else:
                pg.locator('#nxdock .nxd-cells a').nth(idx[0]).hover(); pg.wait_for_timeout(700)
                loc=pg.locator('a[href$="%s"]:visible' % f).filter(has_not=pg.locator('#nxdock .nxd-cells a'))
                cnt=pg.evaluate("(f)=>[...document.querySelectorAll('a[href$=\"'+f+'\"]')].filter(a=>a.getClientRects().length&&!a.closest('.nxd-cells')).length",f)
                if cnt==0:
                    pg.locator('#nxdock .nxd-cells a').nth(idx[0]).click(); pg.wait_for_timeout(700)
                    cnt=pg.evaluate("(f)=>[...document.querySelectorAll('a[href$=\"'+f+'\"]')].filter(a=>a.getClientRects().length&&!a.closest('.nxd-cells')).length",f)
                if cnt==0: res='FAIL пункта нет во всплывающем списке (группа %s)'%grp
                else:
                    pg.evaluate("(f)=>[...document.querySelectorAll('a[href$=\"'+f+'\"]')].filter(a=>a.getClientRects().length&&!a.closest('.nxd-cells'))[0].click()",f); pg.wait_for_url(lambda u: u.split('?')[0].endswith(f),timeout=9000); pg.wait_for_timeout(800)
                    res='OK' if pg.url.split('?')[0].endswith(f) else 'FAIL url '+pg.url[-30:]
            t=pg.title()
            if res=='OK' and ('404' in t or 'Not Found' in t): res='FAIL 404 '+t
        except Exception as e: res='ERR '+str(e)[:80]
        print('R:',grp,f,res,errs[:1]); ctx.close()
    b.close()
P
timeout 285 $PY -I /tmp/s3_cu2.py 2>&1 | cut -c1-300
