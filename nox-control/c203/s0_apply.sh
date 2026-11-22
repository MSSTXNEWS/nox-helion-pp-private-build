#!/bin/bash
# c202: S1_00 hotfix  
B=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main
mkdir -p /tmp/v7deploy; for i in 1 2 3; do curl -fsSL "$B/nox-control/wow7/deploy/S1_00_hotfix.sh?cb=$RANDOM" -o /tmp/v7deploy/S1_00_hotfix.sh && break; sleep 20; done
bash /tmp/v7deploy/S1_00_hotfix.sh 2>&1 | tail -c 2800
