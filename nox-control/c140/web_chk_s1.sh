#!/bin/bash
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/s1web/wow
for f in nox-wow.js chat.html; do echo "$f deployed=$(sha256sum /root/nox/web/$f | cut -c1-12) repo=$(curl -fsSL $R/$f | sha256sum | cut -c1-12)"; done
grep -c "tts/session" /root/nox/web/nox-wow.js; grep -o "speak: '[a-z]*'" /root/nox/web/nox-wow.js | head -1
curl -s -m 5 -o /dev/null -w "web=%{http_code}\n" http://127.0.0.1:8091/web/chat.html; pgrep -af web_server | cut -c1-100
