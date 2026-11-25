#!/bin/bash
S=/workspace/nox/web/site
grep -n "nwSum" $S/nox-news-x.js | tail -2 | cut -c1-1800
echo ====; grep -o "[^;]\{0,160\}/music/[a-z]*[^;]\{0,200\}" $S/nox-p-media.js | head -5
echo ====; grep -o '<section class="card"><h2>Сгенерировать.\{0,900\}' $S/music.html
echo ====; ls /workspace/nox/state 2>&1 | head; python3 -c "import urllib.request as u;print(u.urlopen('https://lenta.ru/rss/news',timeout=8).status)"; python3 -c "import urllib.request as u;print(len(u.urlopen('https://archive.org/advancedsearch.php?q=language%3Arussian+AND+mediatype%3Amovies&fl%5B%5D=identifier&rows=3&output=json',timeout=10).read()))"
