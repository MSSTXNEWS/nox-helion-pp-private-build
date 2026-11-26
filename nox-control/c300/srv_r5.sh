#!/bin/bash
cat /workspace/nox/state/p3/persona_gen.json; echo; cat /workspace/nox/state/p3/persona_gen2.json; echo
echo load $(cat /proc/loadavg); top -b -n1 -w 160 | sed -n 7,16p | cut -c1-120
ps -eo pid,pcpu,etimes,args | grep -E "chrome-headless" | grep -v grep | head -3 | cut -c1-90; pgrep -fc chrome-headless
tail -300 /workspace/nox/state/pipe_err.log | grep -o "ms=[0-9]* ok=[A-Za-z]*" | awk '{split($1,a,"=");n++;s+=a[2]; if($2=="ok=True"){k++;ks+=a[2]}} END{print "verdict n",n,"avg_ms",s/n,"ok",k,"ok_avg",ks/k}'
tail -3 /workspace/nox/state/pipe_err.log | cut -c1-150
