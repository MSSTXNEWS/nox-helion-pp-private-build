echo "C300: ac_pin2"
for p in $(pgrep -f "subbase-qwe|--port 8144|--port 8141"); do echo "$p aff $(taskset -cp $p | sed 's/.*: //')"; done
T=$(pgrep -f "distill_v2.py train" | head -1); echo "trainer $T etimes $(ps -o etimes= -p $T)"
ls -t /workspace/nox/distill_v2/*.log /workspace/nox/logs/* /workspace/nox/state/*train* 2>/dev/null | head -5
L=$(ls -t /workspace/nox/logs/*distill* /workspace/nox/logs/*train* /workspace/nox/distill_v2/train*.log 2>/dev/null | head -1); echo log $L
grep -aE "step [0-9]+|s/step|sec/step" $L | tail -14 | cut -c1-220
nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits -l 1 & P=$!; sleep 60; kill $P
