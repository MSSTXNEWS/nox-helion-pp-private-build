#!/bin/bash
N=/workspace/nox; K=$N/ops/v5_knowledge_gpu_20261125; L=$N/ops/v5_live_adapter_20261125
du -sh $K; du -sh $K/* 2>/dev/null | sort -h | tail -4
echo "-- procs/open"; ps aux | grep -E "v5_knowledge_gpu|v5_live_adapter" | grep -v grep | cut -c1-160 | head -5
timeout 30 lsof +D $K 2>/dev/null | head -3; timeout 30 lsof +D $L 2>/dev/null | head -3
echo "-- refs outside own dirs"
timeout 90 grep -rIl "v5_live_adapter_20261125\|v5_knowledge_gpu_20261125" $N/state $N/distill_v2/code $N/autotrain.sh $N/ops/*.py $N/ops/*.sh $N/router /etc/supervisor/conf.d $N/web/pkg 2>/dev/null | head -10
echo "-- live adapter largest"; du -sh $L/* 2>/dev/null | sort -h | tail -3
ls -d $N/ops/v5_*_2026* | head -20
echo "== backups"; df -h /workspace | tail -1
ls -d $N/backups* /workspace/backups* /backup* 2>/dev/null
for p in $N/backups /workspace/backups; do [ -d $p ] && { du -sh $p; ls -lt --time-style=+%F_%H:%M $p | head -8; }; done
crontab -l 2>/dev/null | grep -v '^#' | head -8; ls /etc/cron.d 2>/dev/null
timeout 100 find $N /workspace -xdev -maxdepth 4 -newermt '-26 hours' -type f -size +200M 2>/dev/null | head -12 | xargs -r ls -la --time-style=+%F_%H:%M
