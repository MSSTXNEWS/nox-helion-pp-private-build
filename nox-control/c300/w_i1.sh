echo "C300: w_i1"
N=/workspace/nox; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles
curl -fsSL "$R/w_a11y/diag_page.py?cb=$(date +%s)" -o /tmp/diag_page.py
export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright
timeout 230 $N/venv/bin/python /tmp/diag_page.py index 2>&1 | cut -c1-1800
