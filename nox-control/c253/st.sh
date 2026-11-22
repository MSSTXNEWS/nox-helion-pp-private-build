#!/bin/bash
ps -eo pid,etime,args | grep -E 'exp_driver|llama-server|glm_watch' | grep -v grep | cut -c1-260
ls -la /root/nox/logs/B_* 2>&1 | cut -c1-120; tail -c 500 /root/nox/logs/B_glm_base_current.log
