#!/bin/bash
date -u +%T; cat /root/nox/logs/flash_ab_24.log /root/nox/logs/flash_ab_99.log /root/nox/logs/flash_pick.log 2>/dev/null; grep -o "ngl [0-9]*\|-c [0-9]*" /root/nox/start_glm.sh; curl -s -m3 -o /dev/null -w "health %{http_code}\n" 127.0.0.1:8081/health; pgrep -f glm_watch.sh >/dev/null && echo watch on
