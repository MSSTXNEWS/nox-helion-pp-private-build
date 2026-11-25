S=/workspace/nox/web/site; PY=/workspace/nox/venv/bin/python
echo "== FS1"
cat > /tmp/s3_fs1.py <<'P'
import json,collections
from playwright.sync_api import sync_playwright
n=json.load(open('/workspace/nox/web/site/nav.json',encoding='utf-8'))
files=[i['file'] for g in n['groups'] for i in g['items']]
print('R: pages',len(files))
JS="""()=>{const o={};for(const e of document.querySelectorAll('body *')){if(e.closest('ninja-keys'))continue;let t='';for(const c of e.childNodes)if(c.nodeType==3)t+=c.textContent;t=t.trim();if(!t)continue;const r=e.getBoundingClientRect();if(!r.width||!r.height)continue;const s=getComputedStyle(e);if(s.visibility=='hidden'||s.display=='none')continue;const fs=parseFloat(s.fontSize);if(fs<12){const k=e.tagName.toLowerCase()+'.'+(e.className&&e.className.toString?e.className.toString().split(' ')[0]:'')+'@'+fs;o[k]=(o[k]||0)+1}}return o}"""
tot=collections.Counter()
with sync_playwright() as p:
    b=p.chromium.launch()
    pg0=b.new_context(viewport={'width':1440,'height':900},service_workers='block').new_page(); pg0.goto('http://localhost:8091/web/index.html',wait_until='load'); pg0.wait_for_timeout(3000)
    print('R: tools html', pg0.evaluate("()=>document.getElementById('nxdTools').innerHTML.replace(/<svg.*?<\\/svg>/g,'').replace(/\\s+/g,' ').slice(0,1500)"))
    for f in files:
        ctx=b.new_context(viewport={'width':1440,'height':900},service_workers='block'); pg=ctx.new_page()
        try:
            pg.goto('http://localhost:8091/web/%s'%f,wait_until='load',timeout=20000); pg.wait_for_timeout(2500); o=pg.evaluate(JS)
            for k,v in o.items(): tot[k]+=v
            print('R:',f,sum(o.values()))
        except Exception as e: print('R:',f,'ERR',str(e)[:60])
        ctx.close()
    b.close()
print('R: TOP', tot.most_common(40))
P
timeout 280 $PY -I /tmp/s3_fs1.py 2>&1 | cut -c1-1800
