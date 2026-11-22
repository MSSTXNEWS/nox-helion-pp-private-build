#!/bin/bash
cd /root/nox; ls -la --time-style=+%m-%d_%H:%M web_server.py* | tail -12 | awk '{print $5,$6,$7}'
for f in $(ls -t web_server.py*); do grep -q "_sys_info" $f && { echo "HAS sys: $f"; break; }; done
grep -c "" web_server.py; grep -n "_deep\b\|NOX_DEEP_DIRECT\|_trim_hist" web_server.py | head -5 | cut -c1-120
