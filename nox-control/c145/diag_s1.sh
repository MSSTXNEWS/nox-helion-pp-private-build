#!/bin/bash
# c145: только чтение. Структура веба на S1.
W=/root/nox/web
echo "== chat.html:"; find $W -name 'chat*.html' -printf '%p %s %TY-%Tm-%Td\n'
echo "== html в корне:"; ls $W/*.html 2>/dev/null | xargs -n1 basename | tr '\n' ' '; echo
echo "== wow-файлы:"; find $W -name 'nox-wow*' -o -name 'nox-v14-planet.js' | head -20
echo "== vendor:"; ls $W/vendor | tr '\n' ' '; echo
echo "== planets:"; ls $W/vendor/nox-planets 2>&1 | tr '\n' ' '; echo
echo "== /vendor/fx:"; ls $W/vendor/fx $W/vendor/nox-extra 2>&1 | head -8 | tr '\n' ' '; echo
echo "== root-relative vendor refs:"; grep -l '"/\./vendor\|"/vendor/' $W/*.html $W/*.js 2>/dev/null | head -20
echo "== curl:"; for p in chat.html classic/chat.html index.html projects.html memory.html training.html models.html system.html settings.html; do echo "$p $(curl -s -o /dev/null -w %{http_code} http://127.0.0.1:8091/web/$p)"; done
