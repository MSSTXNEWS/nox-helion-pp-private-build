#!/bin/bash
W=/root/nox/web
echo "hdri: $(find $W /root/nox -maxdepth 7 \( -iname '*.hdr' -o -iname '*.exr' \) 2>/dev/null | head -3 | tr '\n' ' ')"
echo "onnx: $(find $W/vendor/vad-web -name '*.onnx' | tr '\n' ' ')"
echo "V29: $(find /root /tmp -maxdepth 3 -iname '*WOW_MASTER*' -o -maxdepth 3 -iname '*MISSING_THREE*' 2>/dev/null | head -3 | tr '\n' ' ')"
echo "== routes web_server:"; grep -o '"/api/[a-z_/-]*"' /root/nox/web_server.py | sort -u | head -40 | tr '\n' ' '; echo
echo "== common scripts in index.html:"; grep -o 'src="[^"]*"' $W/index.html | tr '\n' ' ' | cut -c1-600; echo
echo "== memory.html:"; grep -o 'src="[^"]*"' $W/memory.html | tr '\n' ' ' | cut -c1-400; echo; grep -o 'id="[^"]*"' $W/memory.html | head -15 | tr '\n' ' '; echo
echo "== depth:"; grep -l -i 'Максимум\|depth' $W/nox-v14-modes.js $W/nox-newchat.js 2>/dev/null; grep -o -i "'Быстро'.\{0,80\}" $W/nox-v14-modes.js | head -3
echo "== bottom nav:"; grep -l -i 'bottom' $W/nox-shared-chrome-v10.js $W/nox-v14-chrome.js $W/nox-nano-navigation.js 2>/dev/null
echo "== planet bg settings:"; grep -c 'earth' $W/nox-planets.js $W/nox-background-controls.js
