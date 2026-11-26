echo "C300: w_p1"
N=/workspace/nox; S=$N/web/site
for n in studio tv live; do echo "== $n $(wc -c < $S/$n.html)"; grep -o '<script[^>]*>' $S/$n.html | grep -v importmap | sed 's/<script//;s/>//' | grep -v -E 'defer|type="module"' | tr '\n' '|' | cut -c1-600; echo; done
export PATH=$N/tools/node/bin:$PATH
CH=$(ls -d $N/tools/ms-playwright/chromium-*/chrome-linux*/chrome 2>/dev/null | head -1); [ -z "$CH" ] && CH=$N/tools/ms-playwright/chromium_headless_shell-1255/chrome-headless-shell-linux64/chrome-headless-shell
cd $N/tools/uiscore
for n in live studio; do CHROME_PATH=$CH timeout 100 node_modules/.bin/lighthouse http://127.0.0.1:8091/web/$n.html --only-categories=performance --output=json --output-path=/tmp/lh_$n.json --quiet --chrome-flags="--headless=new --no-sandbox --disable-gpu --disable-dev-shm-usage" --form-factor=desktop --screenEmulation.disabled >/dev/null 2>&1
python3 - $n <<'P'
import json,sys
n=sys.argv[1]
try:
    d=json.load(open('/tmp/lh_%s.json'%n));a=d['audits']
    print(n,'perf',round(d['categories']['performance']['score']*100),{k:a[k]['displayValue'] for k in ['first-contentful-paint','largest-contentful-paint','total-blocking-time','speed-index','total-byte-weight','render-blocking-resources','unused-javascript'] if k in a and 'displayValue' in a[k]})
    big=sorted([(i.get('totalBytes',0),i['url'][-50:]) for i in a['network-requests']['details']['items']],reverse=True)[:6];print(big)
except Exception as e: print(n,'ERR',e)
P
done
