#!/bin/bash
ls -la /dev/shm/glm53f /dev/shm/nox_glm | head -30 | cut -c1-160
ls -d /root/nox/glm53* ; ls -la /root/nox/glm53_disk 2>/dev/null | head -20 | cut -c1-160
ps -eo pid,etime,args | grep -E 'wget|curl|hf |huggingface|aria|download|glm_redo|python' | grep -v grep | cut -c1-200 | head
ls -t /root/nox/logs | head -5
