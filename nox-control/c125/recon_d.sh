#!/bin/bash
# разведка: V25 NOX SPACE (погода/курсы/RSS), universe/director: заголовки и зависимости
X=/root/nox/dl/drive/x/V25_FULL_WEB_r3; D=/root/nox/dl/drive
grep -rIl -i "space" $X 2>/dev/null | head -8 | tr '\n' ' '; echo
grep -rIl -iE "open-meteo|cbr-xml|rss" $X 2>/dev/null | head -6 | tr '\n' ' '; echo
echo "## universe js head"; head -c 700 $D/nox-universe-v19.js; echo; echo "## director js head"; head -c 700 $D/nox-owner-director-v20.js; echo
grep -oE "(import|from) ['\"][^'\"]+['\"]" $D/nox-universe-v19.js $D/nox-owner-director-v20.js | sort -u | head -10
