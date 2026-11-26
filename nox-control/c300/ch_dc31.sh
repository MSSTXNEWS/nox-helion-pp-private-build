echo "C300: ch_dc31"
N=/workspace/nox
sleep 100
cut -c1-500 $N/agent/out/dcqa.out
export PATH=$N/tools/node/bin:$PATH
CH=$N/tools/ms-playwright/chromium_headless_shell-1255/chrome-headless-shell-linux64/chrome-headless-shell
cd $N/tools/uiscore && CHROME_PATH=$CH timeout 120 node_modules/.bin/lighthouse http://127.0.0.1:8091/web/chat-dc.html --only-categories=accessibility,best-practices,performance --output=json --output-path=/tmp/lh_dc.json --quiet --chrome-flags="--headless --no-sandbox --disable-gpu" --form-factor=desktop 2>&1 | tail -2 | cut -c1-200
python3 -c "
import json
d=json.load(open('/tmp/lh_dc.json'));print('LH',{k:round(v['score']*100) for k,v in d['categories'].items()})" 2>&1 | tail -1
