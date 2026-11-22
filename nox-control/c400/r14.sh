#!/bin/bash
W=/root/nox/repo/nox-control/wow7
cd $W/GENOME/tests 2>/dev/null && ls | head -5 | tr '\n' ' ' && NOX_STATE=/tmp/c400_gs timeout 200 python3 -B -W ignore -m unittest discover -s . -p 'test*.py' 2>&1 | tail -4
echo TRACE: $(grep -o '"genome[^,]*,[^,]*' /root/nox/state/core_trace/t-a8d12ad93063.json | head -3)
grep -c genome /root/nox/state/core_trace/t-a8d12ad93063.json
python3 -I - <<'PY'
import sys,os
W='/root/nox/repo/nox-control/wow7'; sys.path[:0]=[W,W+'/brain']
os.environ['NOX_STATE']='/tmp/c400_gs2'
import nox_core
c=nox_core.Core()
print('genome_mode',c.genome_mode,'attached',type(c.genome).__name__)
print('v0',c.v0())
PY
echo "IMP rc: $(cat /root/nox/state/c400_imp.rc 2>/dev/null || echo running) $(ls -la /root/nox/state/c400_imp.json | awk '{print $5}')"
