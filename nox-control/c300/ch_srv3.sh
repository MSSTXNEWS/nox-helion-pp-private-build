echo "C300: ch_srv3"
N=/workspace/nox; cb=$(date +%s)
curl -fsSL "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/ch_ui1/pwsw.py?cb=$cb" -o /tmp/pwsw.py
export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright; timeout 160 $N/venv/bin/python /tmp/pwsw.py 2>&1 | cut -c1-700
