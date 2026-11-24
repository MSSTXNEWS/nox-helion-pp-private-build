S=/workspace/nox/web/site
grep -o ".\{60\}\bi_\b.\{60\}" $S/studio.html $S/nox-studio*.js 2>/dev/null | head -5
cat > /tmp/e.py <<'P'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch(args=['--use-gl=swiftshader','--enable-webgl','--ignore-gpu-blocklist'])
    pg=b.new_page(); pg.on('pageerror',lambda x:print('PE',x.message,'|',(x.stack or '')[:300])); pg.on('console',lambda m: print('C',m.text[:150]) if m.type=='error' else None)
    pg.goto('http://127.0.0.1:8091/web/studio.html',wait_until='load'); pg.wait_for_timeout(9000); b.close()
P
cd /tmp; /workspace/nox/venv/bin/python /tmp/e.py 2>&1 | head
for n in index cinema; do python3 -c "
import json;d=json.load(open('$S/qa/rework/$n.json'));print(json.dumps(d,ensure_ascii=False)[:1800])"; done
date; tail -1 $S/qa/history.log
