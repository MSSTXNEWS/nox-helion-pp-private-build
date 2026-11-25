PY=/workspace/nox/venv/bin/python
cat > /tmp/s3_fb.py <<'P'
import json,collections
from playwright.sync_api import sync_playwright
n=json.load(open('/workspace/nox/web/site/nav.json',encoding='utf-8'))
files=[i['file'] for g in n['groups'] for i in g['items']][18:40]
JS="""()=>{const o={};for(const e of document.querySelectorAll('body *')){if(e.closest('ninja-keys,svg,canvas,.excalidraw'))continue;let t='';for(const c of e.childNodes)if(c.nodeType==3)t+=c.textContent;t=t.trim();if(!t)continue;const r=e.getBoundingClientRect();if(!r.width||!r.height)continue;const s=getComputedStyle(e);if(s.visibility=='hidden'||s.display=='none')continue;if(parseFloat(s.fontSize)<12){const k=e.tagName.toLowerCase()+'.'+(e.className&&e.className.toString?e.className.toString().split(' ')[0]:'')+'@'+s.fontSize;o[k]=(o[k]||0)+1}}return o}"""
tot=collections.Counter()
with sync_playwright() as p:
    b=p.chromium.launch()
    for f in files:
        ctx=b.new_context(viewport={'width':1440,'height':900},service_workers='block'); pg=ctx.new_page()
        try:
            pg.goto('http://localhost:8091/web/%s'%f,wait_until='load',timeout=20000); pg.wait_for_timeout(3300); o=pg.evaluate(JS)
            for k,v in o.items(): tot[k]+=v
            print('R:',f,sum(o.values()))
        except Exception as e: print('R:',f,'ERR',str(e)[:60])
        ctx.close()
    b.close()
print('R: TOP', tot.most_common(15))
P
timeout 280 $PY -I /tmp/s3_fb.py 2>&1 | cut -c1-900
