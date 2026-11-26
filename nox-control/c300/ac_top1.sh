echo "C300: ac_top1"
top -b -d 5 -n 12 -w 200 | awk '/^ *[0-9]+ /{c[$12" "$NF]+=$9; n[$12" "$NF]=$1} END{for(k in c)printf "%.0f %s\n", c[k]/11, k}' | sort -rn | head -3 >/dev/null
# per-process avg CPU over 60s via ps delta
ps -eo pid,ni,time,comm,args --no-headers | awk '{print $1}' >/dev/null
snap(){ for p in /proc/[0-9]*; do b=${p#/proc/}; read -r -a s < $p/stat 2>/dev/null || continue; echo "$b $((${s[13]}+${s[14]}))"; done; }
snap > /tmp/s1; sleep 60; snap > /tmp/s2
join <(sort /tmp/s1) <(sort /tmp/s2) | awk '{d=($3-$2)/60; if(d>15)printf "%d %s\n", d, $1}' | sort -rn | head -14 | while read c p; do echo "$c%CPU pid $p ni $(ps -o ni= -p $p) aff $(taskset -cp $p 2>/dev/null|sed 's/.*: //') $(tr '\0' ' ' </proc/$p/cmdline | cut -c1-150)"; done
uptime
T=$(pgrep -f "distill_v2.py train"|head -1); echo trainer aff $(taskset -cp $T|sed 's/.*: //')
grep -aE "скорость" /workspace/nox/agent/autotrain/rounds/r038/train.log | tail -3 | cut -c1-120
