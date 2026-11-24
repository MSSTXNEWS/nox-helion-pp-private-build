#!/bin/bash
f=/workspace/nox/imgsvc/image_service.py; head -30 $f | grep -v "^import\|^from" | cut -c1-180; grep -nE 'path ?== ?"|startswith\("/|elif p|"/[a-z_]+"' $f | head -20 | cut -c1-160
grep -o "mmproj[^ ]*" /proc/$(pgrep -f "port 8104" | head -1)/cmdline 2>/dev/null | head -1; tr '\0' ' ' </proc/$(pgrep -f "port 8104"|head -1)/cmdline | grep -o "\-\-mmproj [^ ]*"
cat /tmp/c300_bt_last 2>/dev/null; tail -6 /workspace/nox/agent/out/c300_bt.log 2>/dev/null | head -0
