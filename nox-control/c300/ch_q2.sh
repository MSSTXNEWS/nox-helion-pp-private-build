echo "C300: ch_q2"
N=/workspace/nox; cb=$(date +%s)
curl -fsSL "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/ch_ui1/pwq2.py?cb=$cb" -o /tmp/pwq2.py
export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright; timeout 110 $N/venv/bin/python /tmp/pwq2.py 2>&1 | cut -c1-400
