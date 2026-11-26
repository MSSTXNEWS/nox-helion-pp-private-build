echo "C300: ch_dc3"
N=/workspace/nox; cb=$(date +%s); R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/ch_dc1
curl -fsSL "$R/pwdc.py?cb=$cb" -o /tmp/dc_pwdc.py
export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright
NOXPORT=8091 timeout 230 $N/venv/bin/python /tmp/dc_pwdc.py 2>&1 | grep -v B64 | cut -c1-400
