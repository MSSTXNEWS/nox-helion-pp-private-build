echo "C300: w_a1"
N=/workspace/nox; cb=$(date +%s)
curl -fsSL "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/w_a11y/axe_scan.py?cb=$cb" -o /tmp/axe_scan.py
export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright
timeout 250 $N/venv/bin/python /tmp/axe_scan.py settings photo calendar 2>&1 | cut -c1-1500
