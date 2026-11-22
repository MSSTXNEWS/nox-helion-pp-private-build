#!/bin/bash
curl -fsSL https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/ui.py -o /tmp/ui.py && python3 /tmp/ui.py
for f in nox_mode.js nox-nav.js nox-wow.js nox-newchat.js; do node -e "new Function(require('fs').readFileSync('/root/nox/web/$f','utf8'))" 2>&1 | head -1 | cut -c1-100 | sed "s/^/$f: /"; done; echo checked
