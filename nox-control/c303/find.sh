#!/bin/bash
date -u +%T; tail -2 /root/nox/logs/flash.log | cut -c1-120; ls -l /dev/shm/glm53f/*00005* | cut -c20-90
find /root/nox/dl/v7 /tmp/nox_v7 /root/nox -maxdepth 6 \( -iname '*eval*' -o -iname '*bench*' -o -iname '*blind*' -o -iname '*soul*' -o -iname '*provoc*' -o -iname '*swap*' -o -iname '*mind*' \) -not -path '*/llama.cpp*' -not -path '*/node_modules/*' -not -path '*/.git/*' -not -name '*.gguf' 2>/dev/null | head -60 > /root/nox/state/evalfind.txt
wc -l /root/nox/state/evalfind.txt; cut -c1-110 /root/nox/state/evalfind.txt | head -45
ls /root/nox/state | head -40
