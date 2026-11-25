S=/workspace/nox/web/site
echo "OUT: pages $(ls $S/*.html | wc -l)"
echo "OUT: $(ls $S/*.html | xargs -n1 basename | tr '\n' ' ')"
echo "OUT: js/css $(ls $S/*.js $S/*.css | xargs -n1 basename | tr '\n' ' ')"
echo "OUT: navjson"; head -c 1800 $S/nav.json; echo
echo "OUT: nox-ds.js size $(wc -c < $S/nox-ds.js)"; head -c 1500 $S/nox-ds.js; echo
echo "OUT: dock/fab ids"; grep -ohE "(id|class)=\"[^\"]*(dock|fab|mini|ask|help|float|chat-bubble|nox-q)[^\"]*\"" $S/*.html $S/nox-*.js 2>/dev/null | sort | uniq -c | sort -rn | head -40
echo "OUT: viewport"; grep -L 'name="viewport"' $S/*.html | head
echo "OUT: ds include count $(grep -l 'nox-ds.js' $S/*.html | wc -l)"
ls /tmp/k2_qa.py && head -20 /tmp/k2_qa.py
