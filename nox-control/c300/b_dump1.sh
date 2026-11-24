S=/workspace/nox/web/site
for p in voice music; do echo "#### $p.html"; cat $S/$p.html | sed -n '/<body/,/<\/body>/p' | cut -c1-6000; done
echo "#### media.js"; wc -c $S/nox-p-media.js; grep -n "voice\|Voice" $S/nox-p-media.js | head -20 | cut -c1-200
echo "#### css classes"; grep -o "^\.[a-z][a-z0-9_-]*" $S/nox-pages.css | sort -u | tr '\n' ' ' | head -c 2500
