#!/bin/bash
echo K_ST2
df -h /workspace | tail -1
tail -n 25 /tmp/r2_audit.log 2>/dev/null | grep -iE 'DONE|median|A/R/U|wow|accept' | tail -15
grep -iE 'accepted|принят' /workspace/nox/web/site/qa/summary.md 2>/dev/null | head -5
