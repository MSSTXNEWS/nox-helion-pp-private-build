echo S4RUN:s4_svc1
S=/workspace/nox/web/site; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/s4_src
cd $S; for f in nox-s4-svc.js nox-s4-projects.css nox-s4-memory.js; do curl -fsSL "$R/$f?t=$(date +%s)" -o $f || exit 1; done
add(){ p=$1; shift; cp -n $p.html $p.html.bak_s4_1; grep -q nox-s4-svc $p.html || sed -i "s|</body>|<script src=\"./nox-s4-svc.js\" data-svc=\"$1\" defer></script>\n</body>|" $p.html; grep -q nox-s4-projects.css $p.html || sed -i 's|</head>|<link rel="stylesheet" href="./nox-s4-projects.css"></head>|' $p.html; echo $p $(grep -c nox-s4-svc $p.html); }
add system "beszel:Мониторинг хоста (Beszel),kuma:Доступность служб (Uptime Kuma)"
add dispatcher "kuma:Доступность служб (Uptime Kuma)"
grep -q nox-s4-memory training.html || sed -i 's|<script src="./nox-theme.js"></script>|<script src="./nox-s4-memory.js"></script><script src="./nox-theme.js"></script>|' training.html; grep -c nox-s4-memory training.html
for p in memory system dispatcher training; do echo "S4 $p $(date -u +%FT%TZ)" > qa/rework/$p.fixed; done
for n in memos radicale beszel actual kuma stirling codeserver; do echo $n $(curl -s -m5 -o /dev/null -w '%{http_code}' 127.0.0.1:8091/svc/$n/); done
curl -s -m5 127.0.0.1:8091/svc/kuma/ | grep -o '\(src\|href\)="/[^"]*"' | head -4
curl -s -m5 127.0.0.1:8091/svc/beszel/ | grep -o '\(src\|href\)="/[^"]*"' | head -4
