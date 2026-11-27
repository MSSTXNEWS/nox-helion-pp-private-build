echo "K1: ln_f2"
export RUNNER_TRACKING_ID=""
N=/workspace/nox; R=$N/web/pkg/webroot; M=127.0.0.1:18220
echo "== A: disk_guard under supervisor"
C=/etc/supervisor/conf.d/nox_disk_guard.conf
if [ ! -e $C ]; then cat > $C <<'Y'
[program:nox_disk_guard]
command=/usr/bin/env DISK_GUARD_MIN_FREE_GB=15 DISK_GUARD_PERIOD=300 bash /workspace/nox/ops/disk_guard.sh --loop
directory=/workspace/nox
autostart=true
autorestart=true
startsecs=3
stdout_logfile=/workspace/nox/agent/out/disk_guard.log
stderr_logfile=/workspace/nox/agent/out/disk_guard.log
Y
fi
supervisorctl reread 2>&1 | tail -1; supervisorctl update 2>&1 | tail -1; sleep 4; supervisorctl status nox_disk_guard | awk '{print $1,$2}'; tail -2 $N/agent/out/disk_guard.log | cut -c1-120
echo "== B: nox_mem adopt"
f0=$(curl -s -m5 $M/health); echo "before $f0"
OLD=$(ss -ltnp | grep ':18220 ' | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2)
kill -TERM $OLD; for i in $(seq 1 15); do ss -ltn | grep -q ':18220 ' || break; sleep 1; done
supervisorctl reset_fail nox_mem >/dev/null 2>&1; supervisorctl start nox_mem 2>&1 | tail -1
sleep 5; supervisorctl status nox_mem | awk '{print $1,$2}'; curl -s -m5 -o /dev/null -w "18220 health %{http_code}\n" $M/health; echo "after $(curl -s -m5 $M/health)"
if ! curl -s -m5 $M/health >/dev/null; then echo "ROLLBACK: manual start"; (cd $N/svc/mem && setsid nohup $N/venv_mem/bin/python $N/svc/mem/nox_mem.py >>$N/svc/logs/mem.log 2>&1 &); sleep 4; curl -s -m5 -o /dev/null -w "18220 after rollback %{http_code}\n" $M/health; fi
echo "== C: minichat on studio/live"
for f in studio live; do P=$R/$f.html; if grep -q "nox-minichat.js" $P; then echo "$f already"; else cp -a $P $P.bak_launch; grep -q "</body>" $P && sed -i 's#</body>#<link rel="stylesheet" href="./nox-minichat.css"><script src="./nox-minichat.js" defer></script></body>#' $P || echo "$f no body tag"; fi; echo "$f -> $(curl -s -m6 -o /dev/null -w '%{http_code}' 127.0.0.1:18091/web/$f.html) has=$(grep -c nox-minichat.js $P)"; done
grep -n "nox-minichat.css" $R/photo.html | head -1 | cut -c1-120
echo "== D: briefs evening"
curl -s -m8 127.0.0.1:18091/api/nox/briefs | python3 -c "
import sys,json;d=json.load(sys.stdin);print({k:(v.get('ok'),v.get('ts'),v.get('mtime')) if isinstance(v,dict) else v for k,v in d.items()})"
date +%s
