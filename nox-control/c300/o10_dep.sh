echo "K1: o10_dep"; export RUNNER_TRACKING_ID=""
N=/workspace/nox; M=$N/mods; S=$N/state/core
B=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/${REF:-main}/nox-control/c300/bundles/organism; cb=$(date +%s)
W=$(mktemp -d); F="nox_org_common nox_ledger nox_organism nox_sleep nox_absorb nox_predator test_nox_organism test_nox_predator"
for f in $F; do curl -fsS -m 30 "$B/$f.py?cb=$cb" -o $W/$f.py || { echo "FETCH_FAIL $f"; echo END; exit 0; }; python3 -m py_compile $W/$f.py || { echo "COMPILE_FAIL $f"; echo END; exit 0; }; done
R=$(cd $W && python3 -W ignore -m unittest test_nox_predator test_nox_organism 2>&1 | tail -3); echo "$R"; echo "$R" | grep -q "^OK" || { echo "TESTS_FAIL abort"; echo END; exit 0; }
PM=$(md5sum $S/passport.json | cut -c1-8); CM=$(md5sum $N/state/agents/sleep_cursor.json 2>/dev/null | cut -c1-8); D0=$(df -BM /workspace | tail -1 | awk '{print $4}')
cp -a $S/self_now.json $S/self_now.json.bak_o10 2>/dev/null
for f in $F; do cp $M/$f.py $M/$f.py.bak_o10 2>/dev/null; cp $W/$f.py $M/$f.py; done
python3 -I $M/nox_ledger.py --verify
D=/etc/supervisor/conf.d
[ -f $D/nox_predator.conf ] || cat > $D/nox_predator.conf <<'CONF'
[program:nox_predator]
command=nice -n 10 python3 -I /workspace/nox/mods/nox_predator.py --daemon
directory=/workspace/nox/mods
autostart=true
autorestart=true
startretries=5
startsecs=3
stopsignal=TERM
stopwaitsecs=10
redirect_stderr=true
stdout_logfile=/workspace/nox/logs/nox_predator.log
stdout_logfile_maxbytes=20MB
stdout_logfile_backups=3
environment=NOX_ROOT="/workspace/nox"
CONF
supervisorctl restart nox_organism 2>&1 | tail -1; supervisorctl reread 2>&1 | tail -1; supervisorctl update 2>&1 | tail -1; sleep 10; supervisorctl status nox_organism nox_predator
echo "guards: passport_same=$([ "$PM" = "$(md5sum $S/passport.json | cut -c1-8)" ] && echo 1 || echo 0) cursor_same=$([ "$CM" = "$(md5sum $N/state/agents/sleep_cursor.json 2>/dev/null | cut -c1-8)" ] && echo 1 || echo 0) disk_free_MB $D0 -> $(df -BM /workspace | tail -1 | awk '{print $4}')"
rm -rf $W; echo END
