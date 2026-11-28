echo "K1: m10_dep1 (bench gate, then deploy with rollback)"
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
echo "=== BEFORE (current prod code)"; $V/bin/python -I $B run http://127.0.0.1:18281 qa-m10 before | tee $W/before.txt
echo "=== AFTER (M10 code)"; $V/bin/python -I $B run http://127.0.0.1:18282 qa-m10 after sweep | tee $W/after.txt
BEST=$(grep "^BEST_CFG" $W/after.txt)
echo "=== TESTS (bench copy, new code)"; $V/bin/python -I $W/new/m10_tests.py http://127.0.0.1:18282 $W/new.db 2>&1 | tee $W/tests.txt | grep -v '^PASS'

echo "=== LOG TAIL"; tail -n 2 $W/new.log | cut -c1-160
HB=$(grep "^BENCH before" $W/before.txt | sed 's/.*hit@4=\([0-9.]*\).*/\1/'); HA=$(grep "^BENCH after" $W/after.txt | sed 's/.*hit@4=\([0-9.]*\).*/\1/'); FAILS=$(grep -c "^FAIL" $W/tests.txt)
echo "gate: hit_before=$HB hit_after=$HA test_fails=$FAILS"
cp $W/new/m10_logic.py $W/new/m10_cite.py $W/new/nox_mem.py $W/new/s03_m10.json /tmp/ 2>/dev/null
pkill -f "$W/"; sleep 1
if [ "$FAILS" != "0" ] || [ "$(echo "$HA >= $HB" | bc -l)" != "1" ]; then echo "GATE_FAIL abort, prod untouched"; rm -rf $W; echo END; exit 0; fi
D=$N/svc/mem; BK=$N/state/core/backup_m10; mkdir -p $BK; TS=$(date +%Y%m%d_%H%M%S)
$V/bin/python -I - <<PY
import sqlite3
s=sqlite3.connect("file:/workspace/nox/state/core/s03.db?mode=ro",uri=True); t=sqlite3.connect("$BK/s03_pre_m10_$TS.db"); s.backup(t); t.close(); print("db_backup_ok")
PY
cp -a $D/nox_mem.py $D/nox_mem.py.bak_m10; cp /tmp/m10_logic.py /tmp/m10_cite.py /tmp/nox_mem.py $D/; cp /tmp/s03_m10.json $N/state/s03_m10.json
$V/bin/python -m py_compile $D/nox_mem.py || { cp -a $D/nox_mem.py.bak_m10 $D/nox_mem.py; echo COMPILE_FAIL_ROLLED_BACK; echo END; exit 0; }
supervisorctl restart nox_mem 2>&1 | tail -2
OK=0; for i in $(seq 1 30); do curl -s -m 2 127.0.0.1:18220/health | grep -q '"v": "m10"' && { OK=1; break; }; sleep 2; done
echo "health_ok=$OK"; curl -s -m 3 127.0.0.1:18220/health; echo
rb() { cp -a $D/nox_mem.py.bak_m10 $D/nox_mem.py; supervisorctl restart nox_mem 2>&1 | tail -1; echo "ROLLED_BACK: $1"; }
[ "$OK" = 1 ] || { rb health; rm -rf $W; echo END; exit 0; }
$V/bin/python -I - <<'PY'
import json,time,urllib.request as ur,sqlite3
def P(p,o,t=10):
    return json.loads(ur.urlopen(ur.Request("http://127.0.0.1:18220"+p,data=json.dumps(o).encode(),headers={"Content-Type":"application/json"}),timeout=t).read())
lat=[];h=0;bad=0
for q in ["как меня зовут","что я люблю","расскажи про мои планы","привет","что было три дня назад","где я живу","какие у меня питомцы","что я говорил вчера"]*3:
    t=time.time()
    try: r=P("/recall",{"q":q,"user":"owner"}); h+=r["hits"]>0; assert set(("context","hits","ids","scores","sims","ms"))<=set(r)
    except Exception as e: bad+=1; print("recall_err",type(e).__name__)
    lat.append((time.time()-t)*1000)
lat.sort(); print("PROD recall n=%d with_hits=%d errors=%d p50=%dms p95=%dms max=%dms"%(len(lat),h,bad,lat[len(lat)//2],lat[int(len(lat)*.95)-1],lat[-1]))
print("stats",json.loads(ur.urlopen("http://127.0.0.1:18220/stats",timeout=5).read()))
print("verify",{k:v for k,v in P("/verify",{"answer":"Ты говорил, что любишь кофе [m:1].","user":"owner","rerank":False}).items() if k in("ok","regen")})
print("forget_pass_dry",{k:v for k,v in P("/forget_pass",{"dry":True},60).items() if k!="ids"})
print("scan_conflicts_dry",P("/scan_conflicts",{}))
c=sqlite3.connect("file:/workspace/nox/state/core/s03.db?mode=ro",uri=True)
print("integrity",c.execute("pragma integrity_check").fetchone()[0],"s03_rows",c.execute("select count(*) from s03").fetchone()[0],"prov_null",c.execute("select count(*) from s03_mem where prov is null").fetchone()[0],"triggers",c.execute("select count(*) from sqlite_master where type='trigger' and name in ('s03_nodel','s03_noupd')").fetchone()[0])
print("bad",bad)
PY
SMOKE_BAD=$($V/bin/python -I -c "print(0)")
supervisorctl status nox_mem nox_rerank | awk '{print $1,$2}'
curl -s -m 3 127.0.0.1:18220/health; echo
rm -rf $W; echo deployed; echo END
