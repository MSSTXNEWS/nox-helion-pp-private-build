echo "C300: ch_dc7"
N=/workspace/nox; cb=$(date +%s); R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/ch_dc1
curl -fsSL "$R/dcqa.py?cb=$cb" -o /tmp/dcqa.py
export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright; export PATH=$N/tools/node/bin:$PATH
(timeout 200 $N/venv/bin/python /tmp/dcqa.py > /tmp/dcqa.out 2>&1 &) 
cd $N/tools/uiscore; echo "== LH direct"; timeout 80 node_modules/.bin/lighthouse http://127.0.0.1:8091/web/chat-dc.html --only-categories=accessibility,best-practices,performance --output=json --output-path=/tmp/lh_dc.json --quiet --chrome-flags="--headless --no-sandbox --disable-gpu" --form-factor=desktop 2>&1 | tail -3 | cut -c1-300
python3 - <<'PY'
import json
try:
    d=json.load(open('/tmp/lh_dc.json'));print('LH',{k:round(v['score']*100) for k,v in d['categories'].items()})
    print([ (a['id'],a['score']) for a in d['audits'].values() if a.get('score') is not None and a['score']<0.9 and a['id'] in('color-contrast','button-name','label','aria-allowed-attr','heading-order','html-has-lang','meta-viewport','tap-targets','target-size','image-alt','link-name','errors-in-console','largest-contentful-paint','total-blocking-time','cumulative-layout-shift')][:10])
except Exception as e: print('LH none',e)
PY
sleep 120; cat /tmp/dcqa.out | cut -c1-700
