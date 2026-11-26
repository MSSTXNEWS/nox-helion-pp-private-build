echo "C300: w_t1"
N=/workspace/nox; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles
curl -fsSL "$R/w_a11y/small_scan.py?cb=$(date +%s)" -o /tmp/small_scan.py
wc -c $N/web/site/nox-theme.js
export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright
timeout 120 $N/venv/bin/python /tmp/small_scan.py 2>&1 | cut -c1-1200
