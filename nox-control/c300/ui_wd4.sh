echo "C300: ui_wd4"
F=/workspace/nox/web/v29src/FASTWOW/site
echo "== cin-worlds.js head"; head -c 2500 $F/nox-cinematic-worlds.js | tr -s ' \n' ' '
echo; echo "== deps"; grep -o "NOX[A-Za-z_]*\|nox-[a-z0-9-]*\.\(js\|css\|mjs\)\|localStorage[^)]*)" $F/nox-cinematic-worlds.js | sort | uniq -c | sort -rn | head -25
echo "== who loads it"; grep -l "nox-cinematic-worlds" $F/*.html | head -5; grep -o '<[^>]*nox-cinematic-worlds[^>]*>' $F/index.html | head
echo "== chooser"; grep -o "data-theme[a-z-]*\|nox-theme-[a-z-]*\|data-world[a-z-]*" $F/nox-cinematic-worlds.js | sort | uniq -c | head
echo "== is nox-wow-max in current site"; ls /workspace/nox/web/site | grep -i "wow-max\|appearance\|cinematic"
