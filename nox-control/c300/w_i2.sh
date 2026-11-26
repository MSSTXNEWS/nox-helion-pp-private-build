echo "C300: w_i2"
N=/workspace/nox; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles
t=$(date +%s)
for f in axe_scan.py small_scan2.py; do curl -fsSL "$R/w_a11y/$f?cb=$t" -o /tmp/$f; done
export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright
timeout 90 $N/venv/bin/python /tmp/small_scan2.py index 2>&1 | cut -c1-1700
timeout 120 $N/venv/bin/python /tmp/axe_scan.py index 2>&1 | cut -c1-900
grep -n -o "api/nox/status[^'\"]*" $N/web/site/index.html $N/web/site/nox-*.js 2>/dev/null | head -5
grep -c 'a11y-fix' $N/web/site/index.html
