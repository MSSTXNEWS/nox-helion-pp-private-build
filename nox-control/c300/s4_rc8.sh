echo S4RUN:s4_rc8
S=/workspace/nox/web/site; sed -n '/<main/,/<\/main>/p' $S/system.html | cut -c1-260 | head -24
grep -n "nox-worlds.css" $S/system.html | head -2; grep -n "\.card\b" $S/nox-worlds.css $S/nox-unify.css $S/nox-pages.css | head -12 | cut -c1-260
