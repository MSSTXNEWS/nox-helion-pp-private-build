#!/bin/bash
cd /root/nox
echo "== grep template"; timeout 100 grep -rIl "Жду твой ввод\|Пустота в очереди" --exclude-dir=dl --exclude-dir=llama.cpp --exclude-dir=node_modules --exclude-dir=.git . /root/.nox* 2>/dev/null | head
echo "== repo status"; git -C repo status --short | head; git -C repo log --oneline -1
echo "== soul headings"; grep -n "^## \|^\[" repo/nox-control/qs6/soul_prompt_ru.txt | cut -c1-80; wc -c repo/nox-control/qs6/soul_prompt_ru.txt
echo "== env gw"; pid=$(ss -ltnp | grep ":8082 " | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2); tr '\0' '\n' </proc/$pid/environ | grep "^NOX" | cut -c1-100
echo "== web_server chat head"; grep -n "def do_POST\|_deep\b\|jid =\|_mode =\|JOBS\[" web_server.py | cut -c1-200 | head -20
sed -n 214,240p web_server.py | cut -c1-250
echo "== wow.js"; grep -n "nox_stage\|nox_phase\|delta\|⏳\|think" web/nox-wow.js | cut -c1-220 | head -30
diff <(sed 's/[[:space:]]*$//' web_server.py) <(sed 's/[[:space:]]*$//' repo/nox-control/s1web/web_server.py) | wc -l
