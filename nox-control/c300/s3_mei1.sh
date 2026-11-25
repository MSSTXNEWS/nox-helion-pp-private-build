#!/bin/bash
S=/workspace/nox/web/site; P=/workspace/nox/web/pkg/server; T=bak_s3_6; PY=/workspace/nox/venv/bin/python
RAW=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300
for f in s3_cmd_patch2.py nox-ninja.js nox-4k.css nox-vt.css; do curl -fsSL "$RAW/$f?v=$(date +%s)" -o /tmp/s3mei_$f || { echo "FETCH FAIL $f"; exit 1; }; done
cp $P/nox_cmd.py $P/nox_cmd.py.$T; cp $S/qa/registry.json $S/qa/registry.json.$T; cp $S/nox-ninja.js $S/nox-ninja.js.$T
rollback(){ echo ROLLBACK; cp $P/nox_cmd.py.$T $P/nox_cmd.py; cp $S/qa/registry.json.$T $S/qa/registry.json; cp $S/nox-ninja.js.$T $S/nox-ninja.js; $P/run_web.sh restart >/dev/null 2>&1; }
$PY /tmp/s3mei_s3_cmd_patch2.py && $PY -m py_compile $P/nox_cmd.py || { rollback; exit 1; }
# убираем zoom из nox-vt.css (теперь nox-4k.css)
grep -v "^@media(min-width:2560px)\|^@media(min-width:3600px)\|^/\* 4K и ТВ" /tmp/s3mei_nox-vt.css > /tmp/s3mei_vt2.css; cp /tmp/s3mei_vt2.css $S/nox-vt.css; cp /tmp/s3mei_nox-4k.css $S/nox-4k.css
for f in $S/*.html; do grep -q nox-vt.css $f || continue; grep -q nox-4k.css $f || sed -i 's#</head>#<link rel="stylesheet" href="./nox-4k.css">\n</head>#' $f; done
cp /tmp/s3mei_nox-ninja.js $S/nox-ninja.js
$P/run_web.sh restart >/tmp/s3_restart2.log 2>&1
ok=0; for i in $(seq 1 20); do c=$(curl -s -m 4 -o /dev/null -w '%{http_code}' localhost:8091/api/chat/health); [ "$c" = 200 ] && ok=1 && break; sleep 3; done
[ $ok = 1 ] || { echo "health fail"; rollback; exit 1; }; echo "health 200"
post(){ curl -s -m 20 -X POST localhost:8091/api/cmd -H 'Content-Type: application/json' -d "$1"; }
echo T-meili; post '{"name":"search.meili","params":{"q":"память"}}' | $PY -c "
import sys,json;j=json.load(sys.stdin);print('ok',j.get('ok'),j.get('error'));h=json.loads(j['result'])['hits'] if j.get('ok') else [];print('hits',len(h));print([(x.get('_index'),sorted(k for k in x if k!='_index')[:8]) for x in h[:2]]);print([str(x.get('title') or x.get('name') or '')[:40] for x in h[:3]])"
echo T-restart-no-token; post '{"name":"svc.restart","params":{"service":"ntfy"}}' | head -c 150; echo
echo T-ntfy-restart-direct; cd $P && $PY -c "
import nox_cmd; print(nox_cmd._b_restart2({'service':'ntfy'}))"
echo T-ntfy-send; post '{"name":"notify.test","params":{}}' | head -c 120; echo
echo T-bad-service; cd $P && $PY -c "
import nox_cmd; print(nox_cmd._b_restart2({'service':'sshd'}))"
c=$(curl -s -m 5 -o /dev/null -w '%{http_code}' localhost:8091/api/chat/health); [ "$c" = 200 ] || { rollback; exit 1; }
$PY /workspace/nox/qa_ctl.py --pin
cat > /tmp/s3_4k2.py <<'P'
import base64,subprocess
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch(); pg=b.new_page(viewport={'width':3840,'height':2160}); pg.goto('http://localhost:8091/web/index.html',wait_until='load'); pg.wait_for_timeout(9000)
    print('4K', pg.evaluate("[innerWidth,document.documentElement.scrollWidth,getComputedStyle(document.documentElement).zoom]"))
    pg.screenshot(path='/tmp/s.png')
    subprocess.run(['ffmpeg','-loglevel','error','-y','-i','/tmp/s.png','-vf','scale=900:-1','-q:v','15','/tmp/s3_k4.jpg'])
    print('B64_k4_BEGIN'); print(base64.b64encode(open('/tmp/s3_k4.jpg','rb').read()).decode()); print('B64_k4_END')
    b.close()
P
$PY -I /tmp/s3_4k2.py 2>&1 | fold -w 900
