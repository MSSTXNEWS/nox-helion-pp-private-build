echo "C300: ui_sc6"
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; export PATH=/workspace/nox/tools/node/bin:$PATH
T=/workspace/nox/tools/uiscore
CP=$(ls /workspace/nox/tools/ms-playwright/chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell | head -1)
timeout 100 $T/node_modules/.bin/lighthouse http://127.0.0.1:8091/web/system.html --only-categories=accessibility --output=json --output-path=/tmp/lhp.json --quiet --chrome-flags="--headless --no-sandbox --disable-gpu" --chrome-path=$CP 2>&1 | head -6 | cut -c1-300
ls -la /tmp/lhp.json 2>&1
/workspace/nox/venv/bin/python - <<'P'
import json,glob,collections
c=collections.defaultdict(lambda:[0,set()])
for f in glob.glob('/workspace/nox/agent/out/ui_sc/*_1440_own.json'):
    d=json.load(open(f))
    for a in d.get('axe',[]): c[a['id']][0]+=a['n']; c[a['id']][1].add(d['page'])
for k,v in sorted(c.items(),key=lambda x:-x[1][0]): print(k,v[0],len(v[1]),sorted(v[1])[:6])
P
