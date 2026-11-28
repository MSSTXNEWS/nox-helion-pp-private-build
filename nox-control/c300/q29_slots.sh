echo "K1: q29_slots"
export RUNNER_TRACKING_ID=""
for p in 8142 8141 8152 8151 8104; do echo "$p $(curl -s -m 5 http://127.0.0.1:$p/slots | python3 -c "
import sys,json
try:
    d=json.load(sys.stdin); print([(x.get('id'),x.get('is_processing'),x.get('n_ctx'),(x.get('next_token') or [{}])[0].get('n_decoded')) for x in d])
except Exception as e: print('err',type(e).__name__)" )"; done
for p in 8142 8141 8152 8151; do pid=$(ss -ltnp | grep "127.0.0.1:$p " | sed 's/.*pid=\([0-9]*\).*/\1/'); echo "$p pid=$pid state=$(awk '{print $3}' /proc/$pid/stat) cpu_s=$(ps -o cputime= -p $pid) thr=$(ls /proc/$pid/task | wc -l) conns=$(ss -tn state established "( sport = :$p )" | tail -n +2 | wc -l) nice=$(ps -o ni= -p $pid)"; done
echo "load: $(cut -d' ' -f1-3 /proc/loadavg) cores=$(nproc)"
echo END
