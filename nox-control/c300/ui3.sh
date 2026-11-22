#!/bin/bash
cd /root/nox/web; grep -o "className *= *'[^']*'\|class=\"[^\"]*\"\|classList.add('[^']*'" nox-wow.js | sort | uniq -c | sort -rn | head -40 | tr '\n' ' '
echo; grep -n "👍\|👎\|thumb\|feedback\|/api/rate\|оценк" nox-wow.js nox_mode.js web_server.py ../web_server.py 2>/dev/null | head -8 | cut -c1-200
grep -n "act(\|acts\|'copy'\|regen\|quote\|branch" nox-wow.js | head -8 | cut -c1-220
ls -la nox_mode.js 2>&1 | cut -c1-80; grep -c "" nox-wow.css 2>/dev/null; grep -o 'href="[^"]*css[^"]*"' chat.html
