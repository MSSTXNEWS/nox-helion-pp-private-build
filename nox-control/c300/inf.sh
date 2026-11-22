#!/bin/bash
echo "== onstart"; cat /root/onstart.sh | cut -c1-200
echo "== gw proc env"; P=$(pgrep -f 'gateway.py' | head -1); echo pid=$P; tr '\0' '\n' < /proc/$P/environ | grep -E '^NOX_' | cut -c1-120; tr '\0' ' ' < /proc/$P/cmdline; echo
echo "== web env"; P=$(pgrep -f 'web_server.py' | head -1); tr '\0' '\n' < /proc/$P/environ | grep -E '^NOX_' | cut -c1-120
echo "== widget"; grep -n "glm_up\|glm_busy" /root/nox/web/nox_mode.js | cut -c1-260
