echo "C300: w_r1"
S=/workspace/nox/web/site; N=/workspace/nox; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles
for k in 1 2 3 4 5 6 7 8; do curl -fsSL "$R/w_roles/nox-roles-x.js?cb=$(date +%s)$k" -o /tmp/rx.js; curl -fsSL "$R/w_roles/roles_add.json?cb=$(date +%s)$k" -o /tmp/ra.json; grep -q '214px' /tmp/rx.js && grep -q scientist /tmp/ra.json && break; sleep 15; done
grep -q '214px' /tmp/rx.js && grep -q scientist /tmp/ra.json || { echo STALE; exit 0; }
cp /tmp/rx.js $S/nox-roles-x.js
cp $S/roles.json $S/roles.json.bak_w_r1
python3 - <<'P'
import json
S='/workspace/nox/web/site/'
c=json.load(open(S+'roles.json'));a=json.load(open('/tmp/ra.json'));n=0
for k,v in a['roles'].items():
    if k not in c['roles']: c['roles'][k]=v;n+=1
json.dump(c,open(S+'roles.json','w'),ensure_ascii=False,indent=1);print('roles added',n,list(c['roles']))
s=open(S+'writer.html',encoding='utf-8').read()
if 'nox-roles-x' not in s:
    i=s.rindex('</body>');open(S+'writer.html','w',encoding='utf-8').write(s[:i]+'<script src="./nox-roles-x.js?v=1" defer></script>\n'+s[i:])
P
bash <(curl -fsSL "$R/th_graphite/ensure.sh?cb=$(date +%s)") 2>&1 | tail -1; bash <(curl -fsSL "$R/th_graphite/webroot_sync.sh?cb=$(date +%s)") | tail -1
cmp $S/roles.json $N/web/pkg/webroot/roles.json && cmp $S/writer.html $N/web/pkg/webroot/writer.html && echo synced
curl -fsSL "$R/w_a11y/axe_scan.py?cb=$(date +%s)" -o /tmp/axe_scan.py
cat > /tmp/rchk.py <<'P'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch()
    for role in ['video','music','cinema','scientist','persona']:
        pg=b.new_page(viewport={'width':1440,'height':900});pg.on('pageerror',lambda e:print('JSERR',role,str(e)[:120]))
        pg.goto('http://127.0.0.1:8091/web/writer.html?role='+role);pg.wait_for_timeout(4500)
        print(role,pg.evaluate("[document.getElementById('rs-title')&&document.getElementById('rs-title').textContent,document.querySelectorAll('#rx-tiles a').length,!!document.getElementById('rs-media')]"))
        pg.close()
P
export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright
timeout 120 $N/venv/bin/python /tmp/rchk.py 2>&1 | tail -8
