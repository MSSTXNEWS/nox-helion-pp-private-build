#!/bin/bash
W=/root/nox/web
echo "== s03 paths:"; grep -o "api('[^']*'\|s03('[^']*'\|path: *'[^']*'" $W/nox-memory.js | sort -u | head -20 | tr '\n' ' '; echo
grep -o "'/api/s03/[a-z_/-]*" /root/nox/web_server.py /root/nox/*.py 2>/dev/null | sort -u | head -15 | tr '\n' ' '; echo
echo "== nav:"; grep -o 'class="[^"]*\(nav\|dock\|menu\|tab\)[^"]*"' $W/memory.html | sort -u | head -8 | tr '\n' ' '; grep -o "className *= *'[^']*\(dock\|bottom\|nav\)[^']*'" $W/nox-v14-shell.js $W/nox-v14-dock.js $W/nox-shared-chrome-v10.js | head -6
echo "== mobile css:"; grep -n -o '@media[^{]*max-width[^{]*' $W/nox-v14-dock.js $W/nox-v14-shell.js $W/nox-shared-chrome-v10.js | head -6
echo "== mic ui:"; grep -l -i 'mic\b\|микрофон' $W/nox-v14-voice.js $W/nox-v14-input.js; grep -o -i ".\{40\}SpeechRecognition.\{50\}" $W/nox-v14-input.js $W/nox-v14-voice.js | head -3
echo "== tts:"; grep -o "/api/tts[a-z/_]*\|speechSynthesis" $W/nox-v14-voice.js | sort | uniq -c | head
curl -s -m4 http://127.0.0.1:8091/api/s03/state | head -c 250
