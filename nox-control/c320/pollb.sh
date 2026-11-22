#!/bin/bash
cd /root/nox/state/flash_bench; ls -la --time-style=+%H:%M | awk '{print $5,$6,$7}' | tail -n +2 | tr '\n' ';'; date +%H:%M
for f in $(ls -t *.json | head -3); do [ -s $f ] && { echo "== $f $(cat ${f%.json}.cfg)"; cut -c1-1000 $f; }; done
tail -c 400 base0.err 2>/dev/null; pgrep -af 'flash_bench' | cut -c1-80; tail -n 3 $(ls -t *.srv.log | head -1) | cut -c1-200
