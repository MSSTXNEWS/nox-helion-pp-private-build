echo "C300: ch_srv1"
N=/workspace/nox; cb=$(date +%s); R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/ch_ui1
for f in golden2.py pwerr.py; do curl -fsSL --retry 5 --retry-all-errors "$R/$f?cb=$cb" -o /tmp/$f || echo FAIL $f; done
setsid -f python3 /tmp/golden2.py > $N/state/ch_golden2.out 2>&1 < /dev/null; echo golden2_started
export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright; timeout 120 $N/venv/bin/python /tmp/pwerr.py 2>&1 | cut -c1-260 | head -70
echo "== web logs"; ls -t $N/state/*web*.log $N/web/*.log $N/logs/*web* 2>/dev/null | head -4
for f in $(ls -t $N/state/*web*.log $N/web/*.log 2>/dev/null | head -2); do echo "-- $f"; grep -a -i "traceback\|error\|exception" $f | tail -12 | cut -c1-220; done
echo "== chat_core / pipe errs"; tail -5 $N/state/pipe_err.log 2>/dev/null | cut -c1-220
echo "== audit"; tail -c 600 $N/state/ch_audit1.log; pgrep -af qa_audit | cut -c1-100 | head -4
