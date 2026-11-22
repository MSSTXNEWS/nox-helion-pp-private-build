#!/bin/bash
df -h /root | tail -1
W=/root/nox/web; ls $W | head -50 | tr '\n' ' '; echo
echo "== vendor:"; ls $W/vendor | tr '\n' ' '; echo
echo "== planets:"; ls $W/vendor/nox-planets $W/vendor/planets $W/assets 2>&1 | head -20 | tr '\n' ' '; echo
echo "== web proc:"; pgrep -af "web_server|8091|http.server" | cut -c1-160 | head; ss -ltnp 2>/dev/null | grep -E ":80(8|9)|:8091" | cut -c1-120
echo "== du:"; du -sh $W 2>/dev/null; du -sh $W/vendor/* 2>/dev/null | sort -h | tail -25
echo "== html:"; ls $W/*.html | xargs -n1 basename | tr '\n' ' '; echo
echo "== lib check:"; for l in split.js dexie cytoscape gridstack vanta ogl pixi silero three sortable fullcalendar; do echo "$l: $(find $W /root/nox -maxdepth 6 -iname "*$l*" 2>/dev/null | head -2 | tr '\n' ' ')"; done
echo "== tools:"; which node npm python3 | tr '\n' ' '; node -v
echo "== git:"; ls /root/nox | head -40 | tr '\n' ' '
