#!/bin/bash
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300; S=/workspace/nox/web/site
for f in tools.html nox-tools.js nox-tools.css tv.html; do curl -fsSL $R/$f -o $S/$f && echo "ok $f $(wc -c <$S/$f)"; done
curl -fsSL $R/dl_libs.py -o /workspace/nox/c300_dl_libs.py && (nohup setsid /workspace/nox/venv/bin/python /workspace/nox/c300_dl_libs.py > /workspace/nox/agent/out/c300_libs.log 2>&1 </dev/null &) && echo "libs download started"
grep -rln "cinema.html" $S --include=*.js --include=*.json --include=*.mjs 2>/dev/null | grep -v "/vendor/\|/lib/" | head
for f in $(grep -rln "cinema.html" $S --include=*.js 2>/dev/null | grep -v "/vendor/\|/lib/\|registry" | head -3); do echo "== $f"; grep -n "cinema.html" $f | head -3 | cut -c1-300; done
