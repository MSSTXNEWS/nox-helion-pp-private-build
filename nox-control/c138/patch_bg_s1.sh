#!/bin/bash
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/s1web/wow
for f in nox-wow.css nox-v14-planet.js nox-wow-bg.js; do for T in $(find /root/nox/web -name $f); do curl -fsSL $R/$f -o $T && echo "patched $T"; done; done
