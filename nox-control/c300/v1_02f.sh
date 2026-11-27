echo "K1: v1_02f"
export RUNNER_TRACKING_ID=""
N=/workspace/nox
date +%T
tail -14 $N/state/chat_fast.log | cut -c1-120
curl -s -m 4 http://127.0.0.1:8104/slots | python3 -c "
import sys,json
for s in json.load(sys.stdin): print('slot',s['id'],'proc',s['is_processing'])"
tail -5 $N/state/s03_recall.log
tail -8 $N/web/restart_k1.log 2>/dev/null | cut -c1-200
ls -t $N/web/*.log $N/web/logs/* 2>/dev/null | head -3
for f in $(ls -t $N/web/*.log 2>/dev/null | head -2); do echo == $f; tail -12 $f | cut -c1-220; done
tail -5 $N/svc/logs/mem.log | cut -c1-200
echo END
