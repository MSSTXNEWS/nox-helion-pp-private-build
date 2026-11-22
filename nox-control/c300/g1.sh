#!/bin/bash
date -u +%T; curl -s -m3 127.0.0.1:8081/health; echo; curl -s -m3 127.0.0.1:8081/slots | python3 -c "import json,sys;print([ (s['id'],s.get('is_processing')) for s in json.load(sys.stdin)])" 2>&1
P=$(pgrep -f 'llama-server.*port 8081'|head -1); ps -o etimes=,pcpu= -p $P; tr '\0' ' ' </proc/$P/cmdline | cut -c60-400; echo
tail -5 /root/nox/logs/glm_8081.log | cut -c1-160; cat /proc/loadavg; ps -eo pcpu,etimes,args --sort=-pcpu | head -6 | cut -c1-120
