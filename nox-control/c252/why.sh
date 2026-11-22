#!/bin/bash
cut -c1-250 /root/nox/start_glm.sh | head -20
ls -t /root/nox/logs | head -8
ps -eo pid,etime,args | grep llama-server | grep -v grep | cut -c1-160
dmesg 2>/dev/null | grep -iE 'killed|oom' | tail -3
L=$(ls -t /root/nox/logs/glm*.log | head -1); echo $L; grep -vE '^\s*$' $L | tail -12 | cut -c1-200
