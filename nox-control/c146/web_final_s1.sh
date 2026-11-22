#!/bin/bash
# c146: итоговая правка веба «Резонанс». Файлы берутся с raw.githubusercontent.com (main). Ничего не удаляется; перед правкой старых страниц делается копия *.bak-c146.
W=/root/nox/web
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/s1web/wow
# 1) чат: только корневой chat.html (classic/ и pc/ не трогаем); стили и скрипт - везде, где лежат под этим именем
curl -fsSL $R/chat.html -o /tmp/c146_chat.html && grep -q 'id="btnThreads"' /tmp/c146_chat.html && cp /tmp/c146_chat.html $W/chat.html && echo "patched $W/chat.html"
for f in nox-wow.css nox-wow.js; do for T in $(find $W -name $f -not -path '*/classic/*'); do curl -fsSL $R/$f -o $T && echo "patched $T"; done; done
curl -fsSL $R/nox-wow-fix.css -o $W/nox-wow-fix.css && echo "put $W/nox-wow-fix.css"
# 2) lottie для чата (были 404)
mkdir -p $W/wow; for f in lottie-ok.json lottie-orbit.json; do [ -s $W/wow/$f ] || { curl -fsSL $R/wow/$f -o $W/wow/$f && echo "put wow/$f"; }; done
# 3) старые страницы: общий файл правок + пути vendor без корневого слэша (lucide и uPlot давали 404)
for p in index projects memory training models system settings; do F=$W/$p.html; [ -f $F ] || continue
  [ -f $F.bak-c146 ] || cp -p $F $F.bak-c146
  grep -q 'nox-wow-fix.css' $F || sed -i 's#</head>#<link rel="stylesheet" href="./nox-wow-fix.css" data-nox-fix="c146"></head>#' $F
done
for p in models system training; do F=$W/$p.html; sed -i 's#src="/\./vendor/#src="./vendor/#g; s#href="/\./vendor/#href="./vendor/#g; s#"/vendor/#"./vendor/#g' $F; done
echo "== остаток корневых путей vendor:"; grep -l '"/\./vendor\|"/vendor/' $W/*.html 2>/dev/null
# 4) проверка
for p in chat.html classic/chat.html index.html projects.html memory.html training.html models.html system.html settings.html nox-wow-fix.css nox-wow.js nox-wow.css wow/lottie-ok.json vendor/fx/uPlot.iife.min.js vendor/nox-extra/lucide.min.js; do echo "$p $(curl -s -o /dev/null -w %{http_code} http://127.0.0.1:8091/web/$p)"; done
echo "CURL chat.html = $(curl -s -o /dev/null -w %{http_code} http://127.0.0.1:8091/web/chat.html)"
