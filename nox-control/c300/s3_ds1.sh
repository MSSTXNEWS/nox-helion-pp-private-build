#!/bin/bash
S=/workspace/nox/web/site; PY=/workspace/nox/venv/bin/python
RAW=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300
for f in nox-ds.css nox-ds.js; do curl -fsSL "$RAW/$f?v=$(date +%s)" -o /tmp/s3ds_$f || { echo FETCHFAIL $f; exit 1; }; done
cp /tmp/s3ds_nox-ds.css $S/nox-ds.css; cp /tmp/s3ds_nox-ds.js $S/nox-ds.js
cp $S/nox-dock-pop.js $S/nox-dock-pop.js.bak_s3_14; cp $S/nav.json $S/nav.json.bak_s3_14
grep -q "nox-ds.css" $S/nox-dock-pop.js || sed -i '1i /* S3-DS */ (function(){if(!document.querySelector("link[href*=\\"nox-ds.css\\"]")){var l=document.createElement("link");l.rel="stylesheet";l.href="./nox-ds.css?v=s3a";document.head.appendChild(l)}if(!window.NOXds&&!document.querySelector("script[src*=\\"nox-ds.js\\"]")){var s=document.createElement("script");s.src="./nox-ds.js?v=s3a";document.head.appendChild(s)}})();' $S/nox-dock-pop.js
n=0; for f in $S/*.html; do grep -q 'nox-unify.css' $f || continue; grep -q 'nox-ds.css' $f || { sed -i 's#</head>#<link rel="stylesheet" href="./nox-ds.css?v=s3a"><script src="./nox-ds.js?v=s3a" defer></script>\n</head>#' $f; n=$((n+1)); }; done; echo "ds linked into $n pages"
$PY - <<'P'
import json
f='/workspace/nox/web/site/nav.json'; n=json.load(open(f,encoding='utf-8'))
g=[x for x in n['groups'] if x['group']=='КОНСТРУКТОР'][0]
if not any(i['file']=='pdf.html' for i in g['items']):
    g['items'].append({'file':'pdf.html','name':'PDF / Документы','title':'NOX HELION · PDF','icon':'file-type-pdf','desc':'Документы и код: PDF, просмотр и правка','soon':False}); n['pages']=int(n.get('pages',0))+1
json.dump(n,open(f,'w',encoding='utf-8'),ensure_ascii=False,indent=1); print('nav: pdf.html added; editor only in hidden')
P
$PY /workspace/nox/qa_ctl.py --pin
cat > /tmp/s3_ds1.py <<'P'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch()
    for pgn in ('index','music','settings','chat'):
        ctx=b.new_context(viewport={'width':1440,'height':900},service_workers='block'); pg=ctx.new_page(); errs=[]; pg.on('pageerror',lambda e: errs.append(str(e)[:100]))
        pg.goto('http://localhost:8091/web/%s.html'%pgn,wait_until='load'); pg.wait_for_timeout(2500)
        print('R:',pgn, pg.evaluate("()=>{const small=[...document.querySelectorAll('body *')].filter(e=>e.children.length==0&&e.textContent.trim()&&parseFloat(getComputedStyle(e).fontSize)<12&&e.getClientRects().length).length;return {ds:!!window.NOXds,css:!!document.querySelector('link[href*=nox-ds.css]'),under12:small}}"), errs[:2])
        ctx.close()
    pg=b.new_page(viewport={'width':1440,'height':900}); pg.goto('http://localhost:8091/web/index.html',wait_until='load'); pg.wait_for_timeout(3000)
    print('R: fixed bottom/top elems', pg.evaluate("()=>[...document.querySelectorAll('body *')].filter(e=>{const s=getComputedStyle(e);return s.position=='fixed'&&e.getBoundingClientRect().height>10}).map(e=>(e.id||e.className.toString().slice(0,24)||e.tagName)+':'+Math.round(e.getBoundingClientRect().top)+'/'+Math.round(e.getBoundingClientRect().height)+'/'+e.children.length).join(' | ')"))
    b.close()
P
timeout 150 $PY -I /tmp/s3_ds1.py 2>&1 | cut -c1-1200
