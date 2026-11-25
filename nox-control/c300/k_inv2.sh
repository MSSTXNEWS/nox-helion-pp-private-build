#!/bin/bash
echo K_INV2
df -h /workspace | tail -1
for d in /workspace/nox/ops/* /workspace/nox/distill_v2/* /workspace/nox/backup; do s=$(du -sh "$d" 2>/dev/null | cut -f1); m=$(stat -c %y "$d" 2>/dev/null | cut -c1-16); echo "SZ $s $m $d"; done | sort -k2 -h | tail -40
echo PROC; ps aux | grep -E 'distill|train|v5_' | grep -v grep | awk '{print $2, $11, $12, $13, $14}' | head -10
