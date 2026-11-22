#!/bin/bash
W=/root/nox/web
df -h /root | tail -1 | tr -s ' '
echo "pc: $(ls $W/pc | head -30 | tr '\n' ' ')"
ss -ltnp | grep -E ":(8091|8090)" | cut -c1-110; pgrep -af web_server | cut -c1-120
echo "== tex:"; find $W -iname '*earth*' -o -iname '*moon*' -o -iname '*mars*' -o -iname '*saturn*' -o -iname '*jupiter*' | head -8
echo "== hdr:"; find $W -iname '*hdr*' -o -iname '*metal*' | head -5
echo "== wp:"; ls $W/workspace-pages | head -20 | tr '\n' ' '; echo; ls $W/assets* $W/vendor/nox-planets 2>&1 | head -10 | tr '\n' ' '
echo "== vad:"; grep -l -i 'vad-web\|MicVAD\|webkitSpeechRecognition' $W/*.js 2>/dev/null | head -5 | tr '\n' ' '
echo "== sortable:"; grep -c -i 'new Sortable' $W/nox-wow-workspace.js $W/nox-wow-widgets.js; grep -o 'src="[^"]*"' $W/widgets.html | head -14 | tr '\n' ' '
