#!/bin/bash
S=/workspace/nox/web/site
grep -o '<script[^>]*src="[^"]*"' $S/photo.html | cut -c1-120
grep -o '<link[^>]*css[^>]*>' $S/photo.html | cut -c1-120
for f in $(grep -o 'nox-[a-z-]*photo[a-z-]*\.js\|nox-p-photo\.js' $S/photo.html | sort -u); do echo "== $f"; grep -n "palette\|theme\|bg-primary" $S/$f | cut -c1-300 | head -8; done
ls $S/nox-*photo* $S/nox-ps* 2>/dev/null
grep -n "\.ps-\|FIE_" $S/nox-pages.css $S/nox-unify.css 2>/dev/null | head -5 | cut -c1-200
grep -rl "ps-ai" $S/*.css | head
head -c 1500 $S/vendor/nox-x/globe/VERSION $S/vendor/nox-x/butterchurn/VERSION
ls $S/vendor/nox-x/filerobot | head
