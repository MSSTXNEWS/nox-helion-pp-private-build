echo "C300: w_r3"
N=/workspace/nox; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles
ok=0; for k in 1 2 3 4 5 6 7 8; do curl -fsSL "$R/w_worlds/matrix.py?cb=$(date +%s)$k" -o /tmp/matrix.py; grep -q MATRIX_DONE /tmp/matrix.py && { ok=1; break; }; sleep 15; done
[ $ok = 1 ] || { echo STALE; exit 0; }
export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright
setsid -f bash -c "$N/venv/bin/python /tmp/matrix.py settings system studio chat-dc > $N/agent/out/w_matrix.jsonl 2>&1" </dev/null >/dev/null 2>&1
echo started
