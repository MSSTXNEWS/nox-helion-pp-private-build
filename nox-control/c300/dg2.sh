cd /workspace/nox/web/site
grep -l "nox-manual" *.js *.html | head; wc -c nox-manual.js; grep -n "nxManual\|display\|hidden\|toggle\|\.css" nox-manual.js | head -30
ls nox-*.css | head -30
