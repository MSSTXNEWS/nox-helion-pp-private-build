#!/bin/bash
O=/workspace/nox/agent/out
for f in adapter_chain_8510 cascade_8400 embed_8082 web_server gb10_judge_tunnel core_8090 nox_agents; do
 echo "=== $f ($(stat -c %s $O/$f.log) B)"
 tail -c 3000000 $O/$f.log | grep -a -E "Traceback|Error|error|Killed|refused|denied|timed out" | sed -E 's/[0-9]{2}:[0-9]{2}:[0-9]{2}[.,0-9]*//; s/[0-9]{4}-[0-9]{2}-[0-9]{2}//; s/0x[0-9a-f]+//g; s/[0-9]+/N/g' | cut -c1-150 | sort | uniq -c | sort -rn | head -4
 tail -2 $O/$f.log | cut -c1-200
done
