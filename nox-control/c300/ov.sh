#!/bin/bash
S=/workspace/nox/web/site; grep -l "Нужна справка старшего\|Вернуть NOX\|Площадка" $S/*.js $S/*.html 2>/dev/null | head; grep -n "Вернуть NOX" $S/*.js 2>/dev/null | head -3 | cut -c1-220
grep -ln "Вернуть NOX\|Площадка" $(grep -o 'src="[^"]*\.js' $S/photo.html | sed 's/src="\.\///;s#^#'$S'/#') 2>/dev/null
grep -o 'import [^;]*' $S/nox-nav.js | head
