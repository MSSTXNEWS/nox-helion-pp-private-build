#!/bin/bash
N=/workspace/nox
grep -n "v5_live_adapter\|v5_knowledge_gpu" $N/distill_v2/code/distill_v2.py | head -5 | cut -c1-200
ps -p 186699 -o pid,etimes,args | cut -c1-200
grep -n "keep\|KEEP\|retain\|days\|find\|rm \|tar \|NOX_BACKUP\|DEST\|dest" $N/agent/nox_backup.sh | head -30 | cut -c1-180
ls -la --time-style=+%F_%H:%M $N/agent/backups $N/backups /workspace/nox_backups 2>/dev/null | head; 
BD=$(grep -o '/workspace[^ "]*backup[^ "]*' $N/agent/nox_backup.sh | head -3); echo "BD=$BD"
for d in $BD; do [ -d $d ] && { du -sh $d; ls -lt --time-style=+%F_%H:%M $d | head -8; }; done
