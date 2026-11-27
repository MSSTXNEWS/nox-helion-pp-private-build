echo "K1: v1_02a"
export RUNNER_TRACKING_ID=""
W=/workspace/nox
cd $W/web/pkg/server 2>/dev/null
echo "LOAD $(cut -d' ' -f1-3 /proc/loadavg) NPROC $(nproc)"
echo "--- slots :8104"
curl -s -m 5 http://127.0.0.1:8104/slots | python3 -c "
import sys,json
for s in json.load(sys.stdin): print('slot',s.get('id'),'proc',s.get('is_processing'),'nctx',s.get('n_ctx'),'ntok',(s.get('next_token') or [{}])[0].get('n_decoded'))" 2>&1 | head
echo "--- other llama ports"
for p in 8101 8102 8103 8104 8105; do printf "$p "; curl -s -m 2 http://127.0.0.1:$p/health | head -c 60; echo; done
echo "--- top cpu"
ps -eo pid,stat,pcpu,etimes,args --sort=-pcpu | head -12 | cut -c1-140 | sed -E 's/(key|token|secret)[^ ]*//Ig'
echo "--- chat_fast.log tail"
for f in $W/web/state/chat_fast.log $W/state/chat_fast.log $(find $W -maxdepth 4 -name chat_fast.log 2>/dev/null|head -2); do [ -f $f ] && { echo $f; tail -25 $f | cut -c1-200; break; }; done
echo "--- s03_recall.log tail"
f=$(find $W -maxdepth 4 -name s03_recall.log 2>/dev/null|head -1); echo $f; tail -15 $f | cut -c1-200
echo "--- markers"
grep -n -E "S03_RECALL|S03_FAST|L1_DEADLINE|id_slot|mem0|extract|owner_active|OWNER_ACTIVE" chat_core.py | cut -c1-170 | head -60
ls $W/state/*.off 2>/dev/null | head -20
echo END
