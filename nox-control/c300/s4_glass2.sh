echo S4RUN:s4_glass2
cd /workspace/nox/web/site; curl -fsSL "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/s4_src/nox-s4-glass.css?t=$(date +%s)" -o nox-s4-glass.css; grep -c "main .wrap .card" nox-s4-glass.css
for p in system dispatcher selffeel soul consciousness organism growth training projects calendar downloads memory settings; do [ -f $p.html ] && { grep -q nox-s4-glass.css $p.html || sed -i 's|</head>|<link rel="stylesheet" href="./nox-s4-glass.css"></head>|' $p.html; }; done
