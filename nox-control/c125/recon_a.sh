#!/bin/bash
# разведка (только чтение): V25_FULL_WEB, WOW_MISSING_THREE, V19 GLASS/CINEMATIC
X=/root/nox/dl/drive/x
for d in V25_FULL_WEB_r3 WOW_MISSING_THREE V19_GLASS_INTERFACE; do echo "## $d"; (cd $X/$d && find . -type f -printf "%P %s\n" | sort | head -60 | awk '{printf "%s(%dK) ", $1, $2/1024}'); echo; done
echo "## V19_CINEMATIC (top)"; (cd $X/V19_CINEMATIC_VISUAL && find . -type f -printf "%P %s\n" | sort | head -30 | awk '{printf "%s(%dK) ", $1, $2/1024}'); echo
