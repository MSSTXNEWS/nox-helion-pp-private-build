#!/bin/bash
a(){ iconv -f utf-8 -t ascii//TRANSLIT -c | cut -c1-140; }
echo "== subexecutors"; grep -rIl -iE "subexecutor|sub_executor" /root/nox/scripts /root/nox/state 2>/dev/null | head -6
F=$(grep -rIl -iE "native_subexecutors" /root/nox/state /root/nox/scripts 2>/dev/null | head -1); echo "file=$F"
[ -n "$F" ] && grep -n -iE "subexecutor" "$F" | head -8 | a
echo "== models by size"; du -sh /root/nox/models/* 2>/dev/null | sort -rh | head -15
echo "== other big"; du -sh /root/nox/state /root/nox/logs /root/.cache /var/log /tmp /root/nox/ops /workspace 2>/dev/null | sort -rh | head -8
echo "== logs biggest"; find /root/nox/logs /var/log -type f -size +100M -exec ls -lh {} \; 2>/dev/null | awk '{print $5,$9}' | head -8
echo "== mem"; free -m | sed -n 2,3p; cat /sys/fs/cgroup/memory.stat 2>/dev/null | grep -E "^(anon|file|shmem|slab) " ; grep -E "Shmem:|Cached:" /proc/meminfo
echo "== tmpfs/shm"; df -h /dev/shm | tail -1; du -sh /dev/shm 2>/dev/null
echo "== procs"; supervisorctl status | grep -c RUNNING; supervisorctl status | grep -E "FATAL" | awk '{print $1}' | tr '\n' ' '
