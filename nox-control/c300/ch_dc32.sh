echo "C300: ch_dc32"
N=/workspace/nox
cut -c1-500 $N/agent/out/dcqa.out | grep -E 'VISION'
export PATH=$N/tools/node/bin:$PATH
ls $N/tools/ms-playwright
CH=$(ls -d $N/tools/ms-playwright/chromium-*/chrome-linux*/chrome 2>/dev/null | head -1); echo "CH=$CH"
[ -z "$CH" ] && CH=$N/tools/ms-playwright/chromium_headless_shell-1255/chrome-headless-shell-linux64/chrome-headless-shell
cd $N/tools/uiscore && CHROME_PATH=$CH timeout 150 node_modules/.bin/lighthouse http://127.0.0.1:8091/web/chat-dc.html --only-categories=accessibility,best-practices,performance --output=json --output-path=/tmp/lh_dc2.json --quiet --chrome-flags="--headless=new --no-sandbox --disable-gpu --disable-dev-shm-usage" --form-factor=desktop --screenEmulation.disabled 2>&1 | head -4 | cut -c1-300
python3 -c "
import json
d=json.load(open('/tmp/lh_dc2.json'));print('LH',{k:round(v['score']*100) for k,v in d['categories'].items()})" 2>&1 | tail -1
