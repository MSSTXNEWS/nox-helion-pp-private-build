echo "C300: ui_wd1"
S=/workspace/nox/web
echo "== files mentioning worlds"; grep -rlI "SOMNIUM" $S/site $S/pkg $S/build /workspace/nox/web 2>/dev/null --include=*.js --include=*.css --include=*.html --include=*.json --include=*.md | head -25
echo "== dirs"; ls $S; ls $S/pkg | head -20; find /workspace -maxdepth 4 \( -iname "*v29*" -o -iname "*5*mir*" -o -iname "*worlds*" \) 2>/dev/null | head -20
echo "== site worlds"; ls -la $S/site | grep -i "world\|theme\|wow\|planet\|palette\|btnset" | cut -c20-120
grep -o "CHRONOS[^;]\{0,80\}" $S/site/nox-worlds.js | head -3; wc -c $S/site/nox-worlds.js $S/site/nox-worlds.css $S/site/nox-planets3d.js
