echo "C300: ui_wd3"
F=/workspace/nox/web/v29src/FASTWOW
cut -c1-220 $F/site/NOX_FIVE_WORLDS_README.md | head -45
echo "== index.html includes"; grep -o '<\(script\|link\)[^>]*\(src\|href\)="[^"]*"' $F/site/index.html | sed 's/<[a-z]* [^>]*\(src\|href\)=//' | tr '\n' ' '
echo; echo "== index vs current: size"; wc -c $F/site/index.html /workspace/nox/web/v29src/V29_3_FROZEN/site/index.html /workspace/nox/web/site/index.html
echo "== sw/ appearance exports"; head -c 900 $F/site/nox-appearance.mjs; echo; grep -o "NOX[A-Za-z]*\s*=" $F/site/nox-cinematic-worlds.js | head -5
echo "== deps ls"; ls $F/site | wc -l; ls $F/site/nox-engines $F/site/vendor | head -60
