#!/bin/bash
ps -eo pid,etimes,pcpu,rss,args --sort=-rss | head -12 | cut -c1-230
ss -ltnp | awk '{print $4, $6}' | grep -oE "[0-9.]+:[0-9]+ .*\"[a-z0-9_.-]+\"" | head -20
ls /workspace/nox | head -20 | tr '\n' ' '; echo; ls /root/nox | tr '\n' ' '; echo; cat /root/onstart.sh | head -15 | cut -c1-200
