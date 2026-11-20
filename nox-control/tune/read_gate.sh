#!/bin/bash
a(){ iconv -f utf-8 -t ascii//TRANSLIT -c | cut -c1-200; }
echo "== gate file"; f=$(find /root/nox -name owner_autonomy_mode_v15.json 2>/dev/null | head -1); echo $f; head -c 900 "$f" | a
echo "== t855u conf"; grep -E "^(command|environment)" /etc/supervisor/conf.d/nox-t855u.conf | a
echo "== modes in code"; grep -nE "FORSAZH|worker_cap|WORKERS" /root/nox/scripts/nox_dispatcher_t855u.py | head -12 | a
grep -nE "PENDING_VERIFIED|autonomy_mode_v15" /root/nox/scripts/owner_autonomy_pool.py | head -8 | a
