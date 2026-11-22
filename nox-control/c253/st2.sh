#!/bin/bash
ps -eo pid,etime,args | grep -E 'llama-server|glm_watch|start_glm' | grep -v grep | cut -c1-160
cat /root/nox/logs/B_restore.out | tail -5; tail -3 /root/nox/logs/glm_watch.log; tail -c 300 /root/nox/logs/glm_8081.log
