S=/workspace/nox/web/site; PY=/workspace/nox/venv/bin/python
echo "== NV16"; ls -l $S/pdf.html $S/editor.html 2>&1 | cut -c1-120
cp $S/nav.json $S/nav.json.bak_s3_13
$PY - <<'P'
import json
f='/workspace/nox/web/site/nav.json'; n=json.load(open(f,encoding='utf-8'))
for g in n['groups']:
    for it in list(g['items']):
        if it['file']=='editor.html': g['items'].remove(it); print('removed editor from',g['group'],it['name'])
        elif 'PDF' in (it.get('name','')+it.get('title','')): print('PDF item before',g['group'],it); it['file']='pdf.html'
pg=n.get('pages')
if isinstance(pg,list) and 'editor.html' in pg: pg.remove('editor.html'); print('pages: editor removed')
if isinstance(pg,dict): pg.pop('editor.html',None)
h=n.get('hidden')
if isinstance(h,list) and 'editor.html' not in h: h.append('editor.html')
json.dump(n,open(f,'w',encoding='utf-8'),ensure_ascii=False,indent=1)
print([i['file'] for g in n['groups'] for i in g['items'] if 'pdf' in i['file'] or 'editor' in i['file']])
P
$PY /workspace/nox/qa_ctl.py --pin
cat > /tmp/s3_nv16.py <<'P'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch(); ctx=b.new_context(viewport={'width':1440,'height':900},service_workers='block'); pg=ctx.new_page(); reqs=[]; errs=[]
    pg.on('request',lambda r: reqs.append(r.url.split('/')[-1]) if '/planets/' in r.url else None); pg.on('response',lambda r: errs.append(r.url[-40:]) if r.status>=400 else None)
    pg.goto('http://localhost:8091/web/settings.html',wait_until='load'); pg.wait_for_timeout(3000)
    pg.evaluate("()=>[...document.querySelectorAll('.nxm-side [role=tab]')].find(b=>/Интерфейс/.test(b.textContent)).click()"); pg.wait_for_timeout(1500)
    pg.evaluate("()=>{const e=document.querySelector('.nxpl');e&&e.scrollIntoView({block:'center'})}"); pg.wait_for_timeout(9000)
    print('R:', pg.evaluate("()=>[(document.querySelector('.nxpl-n')||{}).textContent, document.querySelectorAll('.nxpl-g canvas').length]"), sorted(set(reqs)), errs)
    b.close()
P
timeout 120 $PY -I /tmp/s3_nv16.py 2>&1 | cut -c1-700
