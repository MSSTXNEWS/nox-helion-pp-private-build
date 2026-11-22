#!/bin/bash
cd /root/nox/repo/nox-control 2>/dev/null
echo "== rte conv/trace files"; ls -t /root/nox/state/rte 2>&1 | head -5; ls -t /root/nox/state/trace* /root/nox/state/core* 2>/dev/null | head -5
echo "== last chat turns (rte state)"
python3 - <<'PY'
import glob,json,os
fs=sorted(glob.glob('/root/nox/state/rte/**/*.json*',recursive=True),key=os.path.getmtime)[-3:]
print(fs)
PY
for L in /root/nox/logs/rte*.log /root/nox/logs/core*.log /root/nox/logs/nox_core*.log; do [ -f $L ] && { echo "-- $L"; tail -n 12 $L | cut -c1-230; }; done
