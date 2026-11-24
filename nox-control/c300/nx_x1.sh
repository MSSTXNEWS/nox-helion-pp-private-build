S=/workspace/nox/web/site; P=/workspace/nox/web/pkg/server; V=/workspace/nox/svc; SEC=/workspace/nox/secrets
RAW=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/assets; T=$(date +%s)
for f in events.html manifest.json nox-pwa.js; do curl -fsSL "$RAW/$f?t=$T" -o $S/$f; done
for f in nox_extra.py; do curl -fsSL "$RAW/$f?t=$T" -o $P/$f; done
for f in nox_events.py nox_index.py; do curl -fsSL "$RAW/$f?t=$T" -o $V/$f; done
mkdir -p /tmp/bx $S/vendor/fullcalendar $S/icons && cd /tmp/bx && for f in sw-src.js cal-src.js; do curl -fsSL "$RAW/$f?t=$T" -o $f; done
export PATH=/workspace/nox/tools/node/bin:$PATH
[ -d node_modules/esbuild ] || (npm init -y >/dev/null; npm i esbuild workbox-routing workbox-strategies workbox-expiration @fullcalendar/core @fullcalendar/daygrid @fullcalendar/timegrid @fullcalendar/list @fullcalendar/interaction --no-audit --no-fund 2>&1 | tail -1)
npx esbuild sw-src.js --bundle --minify --format=iife --outfile=$S/sw.js 2>&1 | tail -1
npx esbuild cal-src.js --bundle --minify --format=iife --outfile=$S/vendor/fullcalendar/fc.js 2>&1 | tail -1
cp node_modules/workbox-routing/LICENSE $S/vendor/fullcalendar/LICENSE-workbox 2>/dev/null; cp node_modules/@fullcalendar/core/LICENSE.md $S/vendor/fullcalendar/LICENSE 2>/dev/null
# иконки
cat > /tmp/ic.py <<'P'
from playwright.sync_api import sync_playwright
svg=open('/workspace/nox/web/site/favicon.svg').read()
with sync_playwright() as p:
    b=p.chromium.launch()
    for s in (192,512):
        pg=b.new_page(viewport={'width':s,'height':s}); pg.set_content('<body style="margin:0;background:#02030a;display:grid;place-items:center;height:100vh"><div style="width:72%%;height:72%%">%s</div><style>svg{width:100%%;height:100%%}</style>'%svg)
        pg.screenshot(path='/workspace/nox/web/site/icons/icon-%d.png'%s)
    b.close()
P
/workspace/nox/venv/bin/python /tmp/ic.py; ls -la $S/icons $S/sw.js $S/vendor/fullcalendar | cut -c1-120
# секреты
mkdir -p $SEC; chmod 700 $SEC
[ -f $SEC/web_basic_auth.txt ] || { echo "nox:$(head -c 18 /dev/urandom | base64 | tr -d '/+=' | head -c 20)" > $SEC/web_basic_auth.txt; }
[ -f $SEC/meili_key.txt ] || head -c 24 /dev/urandom | base64 | tr -d '/+=' > $SEC/meili_key.txt
[ -f $SEC/restic_pass.txt ] || head -c 24 /dev/urandom | base64 | tr -d '/+=' > $SEC/restic_pass.txt
chmod 600 $SEC/web_basic_auth.txt $SEC/meili_key.txt $SEC/restic_pass.txt
# meili + restic
cd $V; gh_asset(){ curl -fsSL "https://api.github.com/repos/$1/releases/latest" | python3 -c "
import json,sys,re
for a in json.load(sys.stdin)['assets']:
    if re.search(sys.argv[1],a['name']): print(a['browser_download_url']); break" "$2"; }
mkdir -p meili restic $V/data/meili /workspace/nox/backup
[ -x meili/meilisearch ] || { curl -fsSL "$(gh_asset meilisearch/meilisearch '^meilisearch-linux-amd64$')" -o meili/meilisearch && chmod +x meili/meilisearch; }
[ -x restic/restic ] || { U=$(gh_asset restic/restic 'restic_.*_linux_amd64\.bz2$'); curl -fsSL "$U" | bunzip2 > restic/restic && chmod +x restic/restic; }
./restic/restic version | head -1; ./meili/meilisearch --version | head -1
export RESTIC_REPOSITORY=/workspace/nox/backup/restic RESTIC_PASSWORD_FILE=$SEC/restic_pass.txt
[ -f $RESTIC_REPOSITORY/config ] || ./restic/restic init 2>&1 | tail -1
cat > $V/backup_daily.sh <<'EOF'
#!/bin/bash
export RESTIC_REPOSITORY=/workspace/nox/backup/restic RESTIC_PASSWORD_FILE=/workspace/nox/secrets/restic_pass.txt
while true; do
  /workspace/nox/svc/restic/restic backup /workspace/nox/web/site /workspace/nox/web/pkg /workspace/nox/state /workspace/nox/svc/data /workspace/nox/secrets /workspace/nox/svc/start_all.sh --exclude 'vendor' --exclude '*.bak_*' --exclude 'cache' --exclude 'log' --tag nox-daily >> /workspace/nox/svc/logs/backup.log 2>&1
  /workspace/nox/svc/restic/restic forget --keep-daily 7 --keep-weekly 4 --prune >> /workspace/nox/svc/logs/backup.log 2>&1
  sleep 86400
done
EOF
chmod +x $V/backup_daily.sh
cat >> $V/start_extra.sh <<'EOF'
(echo > /dev/tcp/127.0.0.1/7700) 2>/dev/null || { nohup setsid /workspace/nox/svc/meili/meilisearch --http-addr 127.0.0.1:7700 --db-path /workspace/nox/svc/data/meili --master-key "$(cat /workspace/nox/secrets/meili_key.txt)" --no-analytics --env production >/workspace/nox/svc/logs/meili.log 2>&1 & }
pgrep -f nox_events.py >/dev/null || nohup setsid /workspace/nox/venv/bin/python /workspace/nox/svc/nox_events.py >/workspace/nox/svc/logs/events.log 2>&1 &
pgrep -f "nox_index_loop" >/dev/null || nohup setsid bash -c 'exec -a nox_index_loop bash -c "sleep 20; while true; do /workspace/nox/venv/bin/python /workspace/nox/svc/nox_index.py; sleep 600; done"' >/workspace/nox/svc/logs/index.log 2>&1 &
pgrep -f backup_daily.sh >/dev/null || nohup setsid bash /workspace/nox/svc/backup_daily.sh >/dev/null 2>&1 &
EOF
# патч svc_proxy и теги
cd $P; grep -q nox_extra svc_proxy.py || sed -i 's/^def handle(h, method):/def handle(h, method):\n    if __import__("nox_extra").handle(h, method): return True/' svc_proxy.py
python3 -c "import ast;ast.parse(open('$P/svc_proxy.py').read())" && echo syn-ok
cd $S; n=0; for f in *.html; do grep -q nox-pwa.js "$f" || { sed -i 's#</body>#<link rel="manifest" href="./manifest.json"><script src="./nox-pwa.js" defer></script>\n</body>#' "$f"; n=$((n+1)); }; done; echo pwa-tagged $n
/workspace/nox/web/pkg/server/run_web.sh restart 2>&1 | tail -1
nohup setsid bash $V/start_extra.sh >/dev/null 2>&1 &
sleep 25
curl -s -m5 -o /dev/null -w "cal %{http_code}\n" localhost:8091/cal/events
curl -s -m5 -X POST localhost:8091/cal/events -d '{"title":"Тест NOX","start":"2026-11-25T10:00:00"}' | head -c 150; echo
sleep 20; curl -s -m5 "localhost:8091/search?q=календарь" | head -c 300; echo
curl -s -m5 -H "X-Forwarded-For: 8.8.8.8" -o /dev/null -w "ext-noauth %{http_code}\n" localhost:8091/web/index.html
curl -s -m5 -u "$(cat $SEC/web_basic_auth.txt)" -H "X-Forwarded-For: 8.8.8.8" -o /dev/null -w "ext-auth %{http_code}\n" localhost:8091/web/index.html
curl -s -m5 -o /dev/null -w "local %{http_code}\n" localhost:8091/web/index.html
ls /workspace/nox/backup/restic | head -3; df -h /workspace | tail -1
