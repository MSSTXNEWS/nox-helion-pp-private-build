#!/bin/bash
# b_read_empty.sh: чтение (без изменений) cinema.html, music.html, news.html и списка vendor
set -u
S=/workspace/nox/web/site
echo "== vendor"; ls $S/vendor 2>/dev/null | head -60; ls -d $S/*vendor* $S/lib* $S/js/vendor* 2>/dev/null
for f in cinema music news; do echo "=== $f.html"; cat $S/$f.html | head -c 4000; echo; done
