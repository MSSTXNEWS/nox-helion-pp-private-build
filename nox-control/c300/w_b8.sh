echo "C300: w_b8"
N=/workspace/nox; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles
kill 3344041; sleep 2; ps -eo pid,cmd | grep -c "[w]eb_chat_auth/Caddyfile"
for u in training/status nox/activity notifications settings nox/status; do echo -n "18091 $u "; for i in 1 2 3 4; do curl -s -m6 -o /dev/null -w '%{http_code} ' http://127.0.0.1:18091/api/$u; done; echo; done
mkdir -p /tmp/w18; for f in axe_scan diag_page; do curl -fsSL "$R/w_a11y/$f.py?cb=$(date +%s)" | sed 's/127.0.0.1:8091/127.0.0.1:18091/g' > /tmp/w18/$f.py; done
export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright
timeout 100 $N/venv/bin/python /tmp/w18/axe_scan.py index 2>&1 | cut -c1-330
timeout 60 $N/venv/bin/python /tmp/w18/diag_page.py index 2>&1 | sed 's/.*BAD/BAD/' | cut -c1-330
export PATH=$N/tools/node/bin:$PATH
sed 's#127.0.0.1:8091#127.0.0.1:18091#g' $N/tools/uiscore/score.py > $N/tools/uiscore/score18.py
rm -f $N/agent/out/ui_sc/index_*
timeout 120 $N/venv/bin/python $N/tools/uiscore/score18.py own index 2>&1 | tail -2
python3 $N/tools/uiscore/report.py 2>&1 | grep -E '^index ' | cut -c1-170
rm -f $N/tools/uiscore/score18.py
