echo S4RUN:s4_sl3
S=/workspace/nox/web/site; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/s4_src
cd $S; for f in nox-s4-sl.js nox-s4-projects.css; do curl -fsSL "$R/$f?t=$(date +%s)" -o $f || echo FAIL $f; done
for p in consciousness organism soul selffeel dispatcher system growth training projects calendar downloads memory; do [ -f $p.html ] || continue
 grep -q nox-s4-projects.css $p.html || sed -i 's|</head>|<link rel="stylesheet" href="./nox-s4-projects.css"></head>|' $p.html
 grep -q nox-s4-sl.js $p.html || sed -i 's|</body>|<script src="./nox-s4-sl.js" defer></script>\n</body>|' $p.html
 echo $p $(grep -c nox-s4-sl.js $p.html); echo "S4 $p $(date -u +%FT%TZ): sl-кнопки, стекло" > qa/rework/$p.fixed; done
for p in nexus; do echo "S4 nexus" > qa/rework/nexus.fixed; done
