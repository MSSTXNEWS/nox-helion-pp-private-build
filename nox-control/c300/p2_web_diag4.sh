#!/bin/bash
echo "C300: p2_web_diag4"; N=/workspace/nox
echo "## ops/draw"; ls -la --time-style=long-iso $N/ops/draw 2>&1 | head -30; ls -ld --time-style=long-iso $N/ops $N/ops/draw 2>&1
echo "## def draw_request anywhere"; timeout 100 grep -rl --include=*.py --include=*.bak* 'def draw_request' $N/ops $N/brain $N/web $N/svc $N/agent $N/integration $N/tools 2>/dev/null | head
echo "## nox_core refs"; grep -n 'invoke_draw' $N/brain/BRAIN/nox_core.py | cut -c1-200 | head -5
echo "## backups listing"; ls -la --time-style=long-iso $N/backup 2>/dev/null | tail -15
for t in $(ls -t $N/backup/*.tar* $N/backup/*/*.tar* 2>/dev/null | head -3); do echo "-- $t"; timeout 120 tar -tf "$t" 2>/dev/null | grep -m5 'invoke_draw'; done
echo "## deletion logs mentioning draw"; grep -rhi 'invoke_draw\|ops/draw' $N/agent/out/cleanup*.log $N/agent/out/*janitor*.log $N/disk_janitor*.log 2>/dev/null | tail -10 | cut -c1-200
echo "## recent ops dirs"; ls -lt --time-style=long-iso $N/ops | head -12 | cut -c1-120
echo "## invoke venv has draw?"; ls $N/invoke 2>/dev/null | head; ls $N/invoke_root 2>/dev/null | head -5
echo "## svc registry draw"; grep -n -i 'draw' $N/web/pkg/server/svc_registry.json 2>/dev/null | head -5 | cut -c1-200
echo "## DONE"
