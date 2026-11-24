#!/bin/bash
# b_survey4.sh: только чтение. Состояние sun_adapter :8097, imgsvc :8500, флагов, ссылок студии/фото, 404-ресурсов, VRAM и диска
set -u
W=/workspace/nox
S=$W/web/site
echo "== disk/vram"; df -h $W | tail -1; nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader 2>/dev/null
echo "== services"
for p in 8097 8500 8095 8102; do printf "%s: " $p; curl -s -o /dev/null -w "%{http_code}\n" --max-time 5 http://127.0.0.1:$p/health; done
curl -s --max-time 5 http://127.0.0.1:8097/ | head -c 300; echo
echo "== flags"; cat $W/state/flags.json 2>/dev/null | head -c 1500; echo
echo "== progress"; ls -la $W/ops/controller/ 2>/dev/null | head; tail -n 15 $W/ops/controller/PROGRESS.md 2>/dev/null
echo "== venv_tools"; ls -d $W/venv_tools 2>/dev/null || echo "no venv_tools"
echo "== studio/photo refs"
grep -n "8500\|8097\|/img/\|sun" $S/studio.html $S/photo.html | head -20
echo "== 404 resources"
cd $S && (python3 -m http.server 8777 --bind 127.0.0.1 >/tmp/b_http4.log 2>&1 &); sleep 2
PY=$W/invoke/bin/python; export PLAYWRIGHT_BROWSERS_PATH="$W/tools/ms-playwright"
timeout 300 $PY - <<'PY' 2>&1 | tail -40
from playwright.sync_api import sync_playwright
urls=set()
with sync_playwright() as p:
    b=p.chromium.launch(args=["--no-sandbox"])
    for n in ["chat","studio","photo","music","voice","index"]:
        pg=b.new_page()
        pg.on("response", lambda r: urls.add((r.status, r.url)) if r.status>=400 else None)
        try: pg.goto("http://127.0.0.1:8777/%s.html"%n, wait_until="load", timeout=40000); pg.wait_for_timeout(800)
        except Exception as e: print("fail",n,str(e)[:100])
        pg.close()
    b.close()
for s,u in sorted(urls)[:40]: print(s,u[:150])
PY
pkill -f "http.server 8777" 2>/dev/null; true
