#!/bin/bash
S=/workspace/nox/web/site; PY=/workspace/nox/venv/bin/python; D=$S/vendor/planets
RAW=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300
for f in patch_pl2.py nox-set-search.js nox-mac2.css; do curl -fsSL "$RAW/$f?v=$(date +%s)" -o /tmp/s3st_$f || { echo FETCHFAIL $f; exit 1; }; done
mkdir -p $D/512; for n in 2k_mercury 2k_venus_surface 2k_earth_daymap 2k_moon 2k_mars 2k_jupiter 2k_saturn 2k_uranus 2k_neptune; do ffmpeg -loglevel error -y -i $D/2k/$n.jpg -vf scale=512:-1 -q:v 4 $D/512/$n.jpg; done
ffmpeg -loglevel error -y -i $D/2k/2k_saturn_ring_alpha.png -vf scale=512:-1 $D/512/2k_saturn_ring_alpha.png
du -sh $D/512; ls $D/512 | wc -l
cp $S/nox-planets3d.js $S/nox-planets3d.js.bak_s3_12; cp $S/settings.html $S/settings.html.bak_s3_12
$PY -I /tmp/s3st_patch_pl2.py || exit 1
cp /tmp/s3st_nox-set-search.js $S/nox-set-search.js; cp /tmp/s3st_nox-mac2.css $S/nox-mac2.css
grep -q nox-set-search.js $S/settings.html || sed -i 's#</head>#<link rel="stylesheet" href="./nox-mac2.css">\n<script src="./nox-set-search.js" defer></script>\n</head>#' $S/settings.html
grep -n "nox-set-search\|nox-mac2" $S/settings.html | head -3
$PY /workspace/nox/qa_ctl.py --pin
cat > /tmp/s3_st2.py <<'P'
import base64,subprocess
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch(); ctx=b.new_context(viewport={'width':1440,'height':900},service_workers='block'); pg=ctx.new_page()
    errs=[]; reqs=[]; pg.on('response',lambda r: errs.append(r.status) if r.status>=400 else None); pg.on('request',lambda r: reqs.append(r.url.split('/')[-1]) if 'planets' in r.url else None)
    pg.goto('http://localhost:8091/web/settings.html',wait_until='load'); pg.wait_for_timeout(3500)
    print('R: load ms', pg.evaluate("()=>{const t=performance.getEntriesByType('navigation')[0];return [Math.round(t.domContentLoadedEventEnd),Math.round(t.loadEventEnd)]}"), 'planet reqs before ui tab:', len(reqs), 'errs', errs)
    print('R: search', pg.evaluate("()=>!!document.querySelector('.nxm-search')"))
    pg.evaluate("()=>[...document.querySelectorAll('.nxm-side [role=tab]')].find(b=>/Интерфейс/.test(b.textContent)).click()"); pg.wait_for_timeout(9000)
    print('R: after ui tab', pg.evaluate("()=>[(document.querySelector('.nxpl-n')||{}).textContent, document.querySelectorAll('.nxpl-g canvas').length]"), 'reqs', sorted(set(reqs))[:14], 'errs', errs)
    print('R: tab h', pg.evaluate("()=>Math.round(document.querySelector('.nxm-side [role=tab]').getBoundingClientRect().height)"))
    pg.evaluate("()=>{const i=document.querySelector('.nxm-search');i.value='голос';i.dispatchEvent(new CustomEvent('sl-input',{bubbles:true}))}"); pg.wait_for_timeout(800)
    print('R: search голос visible sections', pg.evaluate("()=>[...document.querySelectorAll('section.setg')].filter(s=>!s.classList.contains('nxt-off')).map(s=>(s.querySelector('h3')||{}).textContent).slice(0,6)"))
    pg.screenshot(path='/tmp/s.png'); subprocess.run(['ffmpeg','-loglevel','error','-y','-i','/tmp/s.png','-vf','scale=1000:-1','-q:v','8','/tmp/s.jpg'])
    print('B64_BEGIN'); print(base64.b64encode(open('/tmp/s.jpg','rb').read()).decode()); print('B64_END'); b.close()
P
timeout 150 $PY -I /tmp/s3_st2.py 2>&1 | fold -w 900
