#!/bin/bash
cd /root/nox; for f in web_server.py web_server.py.bak-173 $(ls -t web_server.py.bak_sl_* web_server.py.bak_dm_* 2>/dev/null); do echo "$(stat -c '%y %s' $f | cut -c12-19,36-) $f dmem=$(grep -c '_dmem()' $f) slot=$(grep -c id_slot $f) pcm=$(grep -c pc_metrics $f) sys=$(grep -c _sys_info $f) health=$(grep -c '/api/health' $f)"; done
grep -n "api/health\|pc_metrics\|^def \|^import\|^from\|^# ----" web_server.py | head -30 | cut -c1-140
