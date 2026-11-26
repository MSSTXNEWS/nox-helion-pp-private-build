#!/bin/bash
P=$(pgrep -f "distill_v2.py train" | head -1); echo trainer $P ni=$(ps -o ni= -p $P) $(grep Cpus_allowed_list /proc/$P/status)
echo load $(cat /proc/loadavg)
nvidia-smi dmon -s u -c 20 -d 1 2>/dev/null | awk 'NR>2{s+=$2;n++; if($2<30)l++} END{print "gpu sm avg",s/n,"samples<30%:",l,"/",n}'
top -H -b -n 2 -d 5 -p $P | awk '/^top/{c++} c==2 && NR>7' | head -8
echo == top cpu
top -b -n 1 -w 200 | sed -n 7,22p | cut -c1-130
echo == per-cpu busy
mpstat -P ALL 3 1 2>/dev/null | tail -34 | awk '{printf "%s:%s ",$3,100-$NF}' | head -c 600; echo
