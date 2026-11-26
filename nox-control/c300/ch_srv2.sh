echo "C300: ch_srv2"
N=/workspace/nox; cb=$(date +%s)
curl -fsSL "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/ch_ui1/pwerr.py?cb=$cb" -o /tmp/pwerr.py
export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright; timeout 150 $N/venv/bin/python /tmp/pwerr.py 2>&1 | tr -d '\n ' | cut -c1-2500; echo
echo "== golden2"; cat $N/state/ch_golden2.out | cut -c1-240
echo "== judge timeouts today"; grep -c "timed out" $N/state/pipe_err.log; grep -a "Traceback" -A4 $N/state/pipe_err.log | tail -12 | cut -c1-200
echo "== chat_core errs"; ls -t $N/state/*chat*err* $N/state/*.err 2>/dev/null | head -3
curl -s -m4 localhost:8300/health | cut -c1-200; echo; curl -s -m4 localhost:8300/ | cut -c1-200
