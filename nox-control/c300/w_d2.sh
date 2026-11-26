echo "C300: w_d2"
N=/workspace/nox; cb=$(date +%s); R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles
curl -fsSL "$R/w_a11y/axe_diag.py?cb=$cb" -o /tmp/axe_diag.py
export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright
timeout 200 $N/venv/bin/python /tmp/axe_diag.py 2>&1 | cut -c1-2000
