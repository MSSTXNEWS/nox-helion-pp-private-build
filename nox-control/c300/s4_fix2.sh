echo S4RUN:s4_fix2
S=/workspace/nox/web/site; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/s4_src
cd $S; curl -fsSL "$R/nox-s4-glass.js?t=$(date +%s)" -o nox-s4-glass.js
for p in growth; do grep -q nox-s4-glass.js $p.html || sed -i 's|</body>|<script src="./nox-s4-glass.js" defer></script>\n</body>|' $p.html; done
for p in training projects calendar events dispatcher system downloads growth consciousness; do echo "S4 $(date -u +%FT%TZ): раскладка лидера, стекло, живые данные" > qa/rework/$p.fixed; done
ls qa/rework/*.fixed | wc -l; ls qa/rework/*.json | head -30
