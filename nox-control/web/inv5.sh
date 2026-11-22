#!/bin/bash
W=/root/nox/web
echo "planets: $(ls $W/assets/nox-approved/planets | tr '\n' ' ')"
echo "== planets.js:"; head -c 700 $W/nox-planets.js; echo
echo "== memory api:"; grep -o "fetch([^)]*)" $W/nox-memory.js | sort -u | head -8
echo "== mic:"; grep -o -i ".\{50\}MicVAD.\{60\}\|.\{40\}webkitSpeechRecognition.\{40\}" $W/nox-v14-input.js $W/nox-chat.js | head -4
echo "== srv gzip/cache:"; grep -n -i 'gzip\|Cache-Control\|Content-Encoding' /root/nox/web_server.py | head -6
echo "== modes in newchat:"; grep -n -i 'depth\|Глубоко' $W/nox-newchat.js | head -6 | cut -c1-160
echo "== chat send:"; grep -n "api/chat" $W/nox-newchat.js | head -4 | cut -c1-200
echo "== health /api/life:"; curl -s -m4 http://127.0.0.1:8091/api/life | head -c 300
