#!/bin/bash
grep -rln "Слышу вас" /root/nox/web /root/nox/web_server.py /root/nox/repo/nox-control/glm53 /root/nox/repo/nox-control/wow7 /root/nox/repo/nox-control/qs6 2>/dev/null | head
grep -rn "Слышу вас" /root/nox/web/*.js /root/nox/web_server.py /root/nox/repo/nox-control/glm53/*.py 2>/dev/null | head -5 | cut -c1-200
echo ==; grep -n "Говори, что нужно\|кратко" /root/nox/repo/nox-control/qs6/soul_prompt_ru.txt | head -5 | cut -c1-200; wc -c /root/nox/repo/nox-control/qs6/soul_prompt_ru.txt
echo ==; curl -s -m3 http://127.0.0.1:8091/ -o /dev/null -w "%{redirect_url}\n"; ls /root/nox/web/*.html | head -20 | tr '\n' ' '
echo; grep -n "thumb\|👍\|rate\b\|оценк" /root/nox/web/nox-wow.js | head -5 | cut -c1-160
