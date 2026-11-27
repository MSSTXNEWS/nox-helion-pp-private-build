echo "K1: rs_tune"
export RUNNER_TRACKING_ID=""
N=/workspace/nox; C=$N/web/pkg/server/chat_core.py
cp -a $C $C.bak_rstune_$(date +%s)
sed -i 's/with ur.urlopen(rq, timeout=14) as r/with ur.urlopen(rq, timeout=9) as r/; s/cf.as_completed(fs, timeout=15)/cf.as_completed(fs, timeout=10)/; s/if len(res) >= 3: break/if len(res) >= 2: break/' $C
python3 -m py_compile $C && echo compile_ok || { cp -a $(ls -t $C.bak_rstune_* | head -1) $C; echo REVERTED; }
grep -c "timeout=9) as r" $C
curl -sfL "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/owner/relaunch.py?cb=$(date +%s)" -o /tmp/relaunch.py
pid=$(ss -ltnp | grep "127.0.0.1:8091 " | sed 's/.*pid=\([0-9]*\).*/\1/'); python3 /tmp/relaunch.py $pid $N/web/restart_k1.log http://127.0.0.1:8091/health 2>&1 | tail -1
sleep 4; echo "health $(curl -s -m5 -o /dev/null -w %{http_code} http://127.0.0.1:18091/api/health)"
