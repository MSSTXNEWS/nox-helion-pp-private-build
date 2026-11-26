echo "C300: ac_pin1"
samp(){ nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits -l 1 & P=$!; sleep $1; kill $P; }
avg(){ awk '{s+=$1;n++}END{printf "avg %.1f n=%d\n",s/n,n}'; }
echo "== who runs subbase"
for p in $(pgrep -f "subbase-qwe|--port 8144|--port 8141"); do echo "pid $p ppid $(ps -o ppid= -p $p) aff $(taskset -cp $p | sed 's/.*: //') nice $(ps -o ni= -p $p)"; pp=$(ps -o ppid= -p $p); ps -o pid,etimes,args -p $pp | tail -1 | cut -c1-220; ps -o args= -p $(ps -o ppid= -p $pp) | cut -c1-160; done
pgrep -f "subbase-qwe" | head -1 | xargs -I{} sh -c 'tr "\0" " " </proc/{}/cmdline | cut -c1-400'; echo
echo "== BEFORE gpu util 60s"; samp 60 > /tmp/ac_b.txt; avg < /tmp/ac_b.txt
echo "== pin"
T=$(pgrep -f "distill_v2.py train" | head -1); echo trainer aff $(taskset -cp $T | sed 's/.*: //')
for p in $(pgrep -f "subbase-qwe|--port 8144|--port 8141"); do echo "was $(taskset -cp $p | sed 's/.*: //')" ; taskset -a -cp 8-15,24-31 $p >/dev/null && echo "pinned $p"; done
sleep 15
echo "== AFTER gpu util 60s"; samp 60 > /tmp/ac_a.txt; avg < /tmp/ac_a.txt
uptime
echo "== disk refs"
for d in ckpt_keep backup v5_distill100_20261125 v5_live_adapter_20261125 v5_knowledge_gpu_20261125; do echo "-- $d: $(grep -rl "$d" /workspace/nox/ops/*.py /workspace/nox/ops/*.sh /workspace/nox/distill_v2/code /workspace/nox/state/*.json 2>/dev/null | head -4 | tr '\n' ' ')"; done
ls -la --time-style=+%F /workspace/nox/distill_v2/ckpt_keep | head -12
ls /workspace/nox/backup | head -12; du -sh /workspace/nox/backup/* 2>/dev/null | sort -rh | head -6
grep -E "step|s/step|it/s" $(ls -t /workspace/nox/logs/*.log 2>/dev/null | head -3) 2>/dev/null | tail -5 | cut -c1-200
