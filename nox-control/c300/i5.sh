#!/bin/bash
cd /root/nox; for f in $(ls -t web_server.py* | head -14); do echo "$(stat -c '%y' $f | cut -c6-16) $(stat -c %s $f) $f sys=$(grep -c _sys_info $f) wait=$(grep -c _wait_resp $f) self=$(grep -c NOX_SELF_SUMMARY $f) deep=$(grep -c NOX_DEEP_DIRECT $f)"; done
grep -rn "web_server.py" /root/nox/logs/boot.log 2>/dev/null | tail -2; tail -3 /root/nox/logs/boot.log | cut -c1-150; uptime
