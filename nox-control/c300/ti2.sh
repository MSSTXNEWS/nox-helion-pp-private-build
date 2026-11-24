#!/bin/bash
S=/workspace/nox/web/site; wc -c $S/cinema.html $S/nox-nav.js $S/nox-shell.js | head -3
sed -e 's/\s\+/ /g' $S/cinema.html | head -c 1800; echo; echo ====
grep -n "cinema" $S/nox-nav.js $S/nox-shell.js | head -6 | cut -c1-260
