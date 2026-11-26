#!/bin/bash
pkill -f "lm_eval" ; pkill -f run_eval.sh; echo killed eval
T=$(pgrep -f "distill_v2.py train" | head -1); echo trainer $T $(grep Cpus_allowed_list /proc/$T/status)
echo "== threads of trainer by cpu"; top -H -b -n 2 -d 3 -p $T | awk '/^top/{c++} c==2 && NR>7' | head -6
echo "== per-thread psr of busy procs (5 samples), only cores 0-3,16-19"
for i in 1 2 3 4 5; do ps -eLo pid,tid,psr,pcpu,ni,comm,args --no-headers | awk '$4>8 && (($3<=3)||($3>=16&&$3<=19)) {print $1,$3,$4,$5,$6}' ; sleep 1; done | sort | uniq -c | sort -rn | head -25
echo "== affinity of top consumers"
for p in $(ps -eo pid --sort=-pcpu | head -25 | tail -24); do echo "$p $(grep Cpus_allowed_list /proc/$p/status | cut -f2) ni=$(ps -o ni= -p $p) $(ps -o pcpu= -p $p) $(tr '\0' ' ' </proc/$p/cmdline | cut -c1-60)"; done
