echo "K1: m10_bench1 (read-only to prod; bench on copies)"
export RUNNER_TRACKING_ID=""
N=/workspace/nox; V=$N/venv_mem; W=/tmp/m10b; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/${REF:-main}/nox-control/c300/m10
pkill -f "$W/" 2>/dev/null; rm -rf $W; mkdir -p $W/new $W/old $W/state/core
for f in m10_logic.py m10_cite.py nox_mem.py m10_bench.py m10_tests.py s03_m10.json; do curl -fsSL $R/$f -o $W/new/$f || { echo FETCH_FAIL $f; echo END; exit 0; }; done
cp $N/svc/mem/nox_mem.py $W/old/nox_mem.py; sed -i 's/18220/18281/g' $W/old/nox_mem.py
$V/bin/python -I - <<'PY'
import sqlite3
for d in ("old","new"):
    s=sqlite3.connect("file:/workspace/nox/state/core/s03.db?mode=ro",uri=True); t=sqlite3.connect("/tmp/m10b/%s.db"%d); s.backup(t); t.close()
print("copies_ok")
PY
echo "disk_free_G=$(df -BG / | tail -1 | awk '{print $4}')"
(cd $W/old && NOX_S03_DB=$W/old.db setsid nohup $V/bin/python $W/old/nox_mem.py > $W/old.log 2>&1 < /dev/null &)
cp $W/new/s03_m10.json $W/state/s03_m10.json
(cd $W/new && NOX_STATE=$W/state NOX_S03_DB=$W/new.db NOX_MEM_PORT=18282 setsid nohup $V/bin/python $W/new/nox_mem.py > $W/new.log 2>&1 < /dev/null &)
for i in $(seq 1 20); do curl -s -m 2 127.0.0.1:18281/health >/dev/null && curl -s -m 2 127.0.0.1:18282/health >/dev/null && break; sleep 2; done
echo "old: $(curl -s -m 2 127.0.0.1:18281/health)"; echo "new: $(curl -s -m 2 127.0.0.1:18282/health)"
B=$W/new/m10_bench.py
$V/bin/python -I $B seed http://127.0.0.1:18281 qa-m10; $V/bin/python -I $B fixts $W/old.db qa-m10
$V/bin/python -I $B seed http://127.0.0.1:18282 qa-m10; $V/bin/python -I $B fixts $W/new.db qa-m10
echo "=== BEFORE (current prod code)"; $V/bin/python -I $B run http://127.0.0.1:18281 qa-m10 before
echo "=== AFTER (M10 code)"; $V/bin/python -I $B run http://127.0.0.1:18282 qa-m10 after sweep | tee $W/after.txt
BEST=$(grep "^BEST_CFG" $W/after.txt)
echo "=== TESTS (bench copy, new code)"; $V/bin/python -I $W/new/m10_tests.py http://127.0.0.1:18282 $W/new.db 2>&1 | tail -40
echo "=== log tails (no texts expected)"; tail -n 3 $W/new.log | cut -c1-200
pkill -f "$W/"; sleep 1; rm -rf $W; echo cleaned; echo END
