#!/bin/bash
echo "C300: p2_web_ctx"; N=/workspace/nox
echo "## chat_core draw usage"; grep -n 'draw_request\|draw_' $N/web/pkg/server/chat_core.py | cut -c1-220 | head -20
echo "## nox_core 1715-1760"; sed -n 1715,1760p $N/brain/BRAIN/nox_core.py | cut -c1-200
echo "## other importers/tests of invoke_draw or ops/draw"; grep -rln 'ops/draw\|invoke_draw' $N --include=*.py --include=*.sh --include=*.json --include=*.md 2>/dev/null | head -12
echo "## nox_mem tgz has ops/draw?"; timeout 200 tar -tzf $N/backup/nox_mem_20261125_031701.tgz 2>/dev/null | grep -m3 -E 'ops/draw|invoke_draw'
echo "## DONE"
