#!/bin/bash
grep -n 'glm_busy\|"/api/sys"\|/api/sys' /root/nox/web_server.py | cut -c1-230
grep -n "glm_up" /root/nox/web/nox_mode.js | cut -c1-300
for f in nox-nav.js nox-wow.js; do node --check /root/nox/web/$f.bak_* 2>&1 | head -2 | cut -c1-120; ls /root/nox/web/$f.bak_* | tail -1; done
head -c 300 /root/nox/web/nox-nav.js; echo; grep -c "" /root/nox/logs/web_server.log; tail -3 /root/nox/logs/web_server.log | cut -c1-200
