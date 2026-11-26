#!/bin/bash
N=/workspace/nox
for d in $N/ops/v5_live_adapter_20261125 $N/ops/v5_knowledge_gpu; do
 echo "== $d"; du -sh $d 2>/dev/null; ls -la --time-style=+%F_%T $d | head -8
 echo "-- open (lsof/fuser)"; timeout 40 lsof +D $d 2>/dev/null | head -5; echo "lsof rc done"
 b=$(basename $d); echo "-- refs"
 timeout 60 grep -rIl --include=*.py --include=*.sh --include=*.json --include=*.yaml --include=*.yml --include=*.conf --include=*.service "$b" $N/ops $N/distill_v2 $N/state $N/router /etc/supervisor/conf.d /etc/systemd/system $N/*.sh 2>/dev/null | head -10
 ps aux | grep -F "$b" | grep -v grep | cut -c1-150 | head -3
done
echo "== ckpt_best_global/autotrain/llama-swap refs"
grep -rIl "v5_live_adapter\|v5_knowledge_gpu" $N/ops/*.py $N/ops/*.sh $N/distill_v2/code $N/autotrain.sh $N/state/*.json 2>/dev/null | head; 
ls -la $N/state/ckpt_best_global* 2>/dev/null | head -3; readlink -f $N/ckpt_best_global 2>/dev/null
grep -rIn "v5_" $(find / -maxdepth 4 -iname '*llama-swap*' \( -name '*.yaml' -o -name '*.yml' \) 2>/dev/null | head -3) 2>/dev/null | head -5
echo "== backups"
df -h /workspace | tail -1
for p in /workspace/backups /workspace/nox/backups /workspace/nox/ops/backup* /backup /workspace/nox_backups; do [ -e $p ] && { echo $p; du -sh $p; ls -lt --time-style=+%F_%H:%M $p | head -8; }; done
crontab -l 2>/dev/null | grep -i "backup\|bak\|rsync\|tar" | head; ls /etc/cron.d 2>/dev/null; grep -ril "backup" /etc/cron.d /etc/cron.daily 2>/dev/null | head
find / -xdev -newermt '-26 hours' -type f -size +300M \( -name '*.tar*' -o -name '*.zst' -o -name '*.gz' -o -name '*.bak*' \) 2>/dev/null | head -8 | xargs -r ls -la --time-style=+%F_%H:%M
