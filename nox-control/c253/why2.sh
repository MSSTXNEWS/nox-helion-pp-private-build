#!/bin/bash
grep -iE 'error|fail|unable|cannot|No such' /root/nox/logs/glm_8081.log | tail -6 | cut -c1-300
ls -la /root/nox/glm53 | head -14 | cut -c1-200
df -h /dev/shm | tail -1; ls /dev/shm | head; ls /dev/shm/nox_glm 2>/dev/null | wc -l; free -g | head -2; uptime
