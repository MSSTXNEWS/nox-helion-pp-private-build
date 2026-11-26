echo "C300: w_a13"
N=/workspace/nox; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles
curl -fsSL "$R/w_a11y/axe_scan.py?cb=$(date +%s)" -o /tmp/axe_scan.py
export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright
timeout 250 $N/venv/bin/python /tmp/axe_scan.py photo live 2>&1 | grep ' 1440 \| 390 ' | cut -c1-1600
grep -c 'data-nox-theme' /workspace/nox/web/site/nox-theme.js; grep -c 'nox-theme' /workspace/nox/web/site/live.html /workspace/nox/web/site/studio.html /workspace/nox/web/site/index.html
