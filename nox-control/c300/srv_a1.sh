#!/bin/bash
S=/workspace/nox/state/speed.json; cp -n $S $S.bak_srv_ckpt
python3 -I - <<'PY'
import json
p="/workspace/nox/state/speed.json"; d=json.load(open(p))
if d.get("ckpt_every")!=50: d["ckpt_every"]=50; d["_ckpt_why"]="SRV 26.11: holdout 94 с на 25 шагов (~15% времени) -> каждые 50; откат: убрать ключ"; json.dump(d,open(p,"w"),ensure_ascii=False,indent=1)
print("ckpt_every",d["ckpt_every"])
PY
echo == df; df -h /workspace / /tmp 2>/dev/null | cut -c1-90
echo == mem; free -m | head -3; echo swap procs:; for p in /proc/[0-9]*; do s=$(awk '/VmSwap/{print $2}' $p/status 2>/dev/null); [ "${s:-0}" -gt 20000 ] && echo "$(basename $p) ${s}kB $(tr '\0' ' ' <$p/cmdline | cut -c1-70)"; done | sort -k2 -rn | head -5
echo == zombies; ps -eo stat,pid,ppid,etimes,args | awk '$1 ~ /^Z/' | head -10 | cut -c1-120; ps -eo stat | grep -c '^Z'
echo == Dstate; ps -eo stat,pid,etimes,wchan:20,args | awk '$1 ~ /^D/' | head -8 | cut -c1-140
echo == oom; dmesg 2>/dev/null | grep -i -E "out of memory|oom-kill|killed process" | tail -5; journalctl --since "24 hours ago" -p err --no-pager 2>/dev/null | tail -5
echo == logs 24h errors
find /workspace -xdev -name "*.log" -mmin -1440 -size +0 -not -path "*/venv/*" -not -path "*/node_modules/*" -not -path "*/site-packages/*" -not -path "*/invoke_root/*" 2>/dev/null | head -400 > /tmp/logs.txt; wc -l < /tmp/logs.txt
while read f; do n=$(tail -c 3000000 "$f" 2>/dev/null | grep -a -c -E "Traceback|CRITICAL|\bFATAL\b|Segmentation|CUDA error|out of memory|OutOfMemory|Killed|Permission denied|Connection refused"); [ "$n" -gt 0 ] && echo "$n $f"; done < /tmp/logs.txt | sort -rn | head -30
