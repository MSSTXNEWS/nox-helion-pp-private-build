echo S4RUN:s4_gr2
cd /workspace/nox/web/site; curl -fsSL "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/s4_src/nox-s4-glass.js?t=$(date +%s)" -o nox-s4-glass.js
for p in growth; do grep -q nox-s4-glass.js $p.html || sed -i 's|</body>|<script src="./nox-s4-glass.js" defer></script>\n</body>|' $p.html; grep -c "nox-s4-glass.js" $p.html; done
grep -o 'data-page="[a-z]*"' growth.html system.html | head
grep -n "dataZoom" nox-brain-x.js | cut -c1-120 | head -4
