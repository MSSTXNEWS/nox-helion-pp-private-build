#!/bin/bash
a(){ iconv -f utf-8 -t ascii//TRANSLIT -c | cut -c1-260; }
E=/root/nox/models/engram_ram.gguf
echo "== engram file"; ls -laL $E 2>&1 | a; stat -L -c%s $E 2>&1; readlink $E 2>&1 | a
echo "== holder svc"; supervisorctl status nox-engram-cold-holder | a
grep -rh -A8 "program:nox-engram-cold-holder" /etc/supervisor/conf.d/ | grep -E "command|autorestart|startsecs" | a
tail -n 6 /var/log/supervisor/nox-engram-cold-holder*.log 2>/dev/null | a
echo "== who holds memfd/engram"; for p in $(pgrep -f "llama-server.*8098|engram"); do ls -l /proc/$p/fd 2>/dev/null | grep -iE "memfd|engram" | head -2 | sed "s/^/pid $p: /" | a; done
echo "== llama maps engram?"; P=$(pgrep -f "llama-server.*8098" | head -1); grep -c engram /proc/$P/maps 2>/dev/null; echo "pid $P"
echo "== cpu topology"; lscpu | grep -E "Model name|Thread|Core|Socket|NUMA node\(s\)|On-line" | a
echo "== top cpu users"; ps -eo pcpu,comm --sort=-pcpu | head -6 | a
