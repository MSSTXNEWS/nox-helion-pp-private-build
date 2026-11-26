echo "C300: w_x1"
S=/workspace/nox/web/site; N=/workspace/nox; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles
ok=0; for k in 1 2 3 4 5 6 7 8; do t=$(date +%s)$k
 curl -fsSL "$R/w_tv/nox-tv-player.js?cb=$t" -o /tmp/tvp.js; curl -fsSL "$R/w_roles/nox-roles-x.js?cb=$t" -o /tmp/rx.js; curl -fsSL "$R/w_writer/nox-writer-pro.js?cb=$t" -o /tmp/wr.js
 grep -q 'defineCustomElement' /tmp/tvp.js && grep -q 'katex' /tmp/rx.js && grep -q 'nox-notes' /tmp/wr.js && { ok=1; break; }; sleep 15; done
[ $ok = 1 ] || { echo STALE; exit 0; }
cp /tmp/tvp.js $S/nox-tv-player.js; cp /tmp/rx.js $S/nox-roles-x.js; cp /tmp/wr.js $S/nox-writer-pro.js
python3 - <<'P'
S='/workspace/nox/web/site/'
s=open(S+'tv.html',encoding='utf-8').read()
if 'nox-tv-player' not in s:
    i=s.rindex('</body>');open(S+'tv.html','w',encoding='utf-8').write(s[:i]+'<script src="./nox-tv-player.js?v=1" defer></script>\n'+s[i:]);print('tv patched')
p=S+'nox-u-pad.js';s=open(p,encoding='utf-8').read()
old='function seq(f){Q=Q.then(f,f);return Q}'
if 'nox-notes' not in s and old in s:
    import shutil;shutil.copy(p,p+'.bak_w_x1')
    s=s.replace(old,"function seq(f){const g=function(){return navigator.locks?navigator.locks.request('nox-notes',f):f()};Q=Q.then(g,g);return Q}");open(p,'w',encoding='utf-8').write(s);print('pad locked')
else: print('pad skip', 'nox-notes' in s, old in s)
P
bash <(curl -fsSL "$R/th_graphite/ensure.sh?cb=$(date +%s)") 2>&1 | tail -1; bash <(curl -fsSL "$R/th_graphite/webroot_sync.sh?cb=$(date +%s)") | tail -1
for f in tv.html nox-tv-player.js nox-roles-x.js nox-writer-pro.js nox-u-pad.js; do cmp $S/$f $N/web/pkg/webroot/$f && echo synced_$f; done
cat > /tmp/xchk.py <<'P'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch()
    for u,q in [('tv','#nxtv-open'),('writer?role=scientist','#rs-media'),('writer','#wr-book')]:
        pg=b.new_page(viewport={'width':1440,'height':900});pg.on('pageerror',lambda e:print('JSERR',u,str(e)[:100]))
        pg.goto('http://127.0.0.1:8091/web/%s'%(u if '?' in u else u+'.html')+('' if '?' not in u else ''));pg.wait_for_timeout(4500)
        print(u,pg.evaluate("!!document.querySelector('%s')"%q));pg.close()
P
export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright
timeout 100 $N/venv/bin/python /tmp/xchk.py 2>&1 | tail -6
curl -fsSL "$R/w_a11y/axe_scan.py?cb=$(date +%s)" -o /tmp/axe_scan.py; timeout 90 $N/venv/bin/python /tmp/axe_scan.py tv 2>&1 | cut -c1-400
grep -E 'AXE|VISION' $N/agent/out/dcqa.out | cut -c1-300
