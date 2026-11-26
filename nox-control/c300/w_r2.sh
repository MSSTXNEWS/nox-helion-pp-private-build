echo "C300: w_r2"
S=/workspace/nox/web/site
grep -o "data-nox-ui-button[^;]\{0,160\}" $S/*.js 2>/dev/null | head -6 | cut -c1-260
grep -o "nox-wow-button-skin[^;]\{0,200\}" $S/*.js 2>/dev/null | head -6 | cut -c1-300
grep -o "button-skin'[^)]\{0,100\}" $S/*.js | head -3
grep -o "ui-button[^;]\{0,100\}" $S/studio.html | head -5 | cut -c1-200
grep -n -o "skins\?\s*[:=]\s*\[[^]]\{0,200\}\]\|SKINS\s*=\s*[^;]\{0,200\}" $S/*.js $S/studio.html 2>/dev/null | head -5 | cut -c1-300
