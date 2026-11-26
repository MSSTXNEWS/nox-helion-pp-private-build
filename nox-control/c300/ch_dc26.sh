echo "C300: ch_dc26"
N=/workspace/nox; cb=$(date +%s); R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles
bash <(curl -fsSL "$R/th_graphite/ensure.sh?cb=$cb") force 2>&1 | tail -2 | cut -c1-200
bash <(curl -fsSL "$R/th_graphite/webroot_sync.sh?cb=$cb") | tail -1; wc -c $N/web/site/nox-theme.js $N/web/pkg/webroot/nox-theme.js
curl -fsSL "$R/ch_dc1/dcreply.py?cb=$cb" -o /tmp/dcreply.py
export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright
timeout 190 $N/venv/bin/python /tmp/dcreply.py 2>&1 | cut -c1-400
echo "== dcqa"; cut -c1-600 $N/agent/out/dcqa.out
