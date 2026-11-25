echo S4RUN:s4_nex1
S=/workspace/nox/web/site; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/s4_src
cd $S; for f in nox-s4-lead.js nox-s4-lead.css; do curl -fsSL "$R/$f?t=$(date +%s)" -o $f || exit 1; done
cp -n nexus.html nexus.html.bak_s4_1
grep -q nox-s4-lead nexus.html || python3 - <<'P'
p='/workspace/nox/web/site/nexus.html';t=open(p).read()
t=t.replace('</head>','<link rel="stylesheet" href="./nox-s4-lead.css"><script src="./vendor/cytoscape/dist/cytoscape.min.js"></script></head>',1)
t=t.replace('</body>','<script src="./nox-s4-lead.js" data-lead="nexus" defer></script>\n</body>',1)
open(p,'w').write(t)
P
echo "S4 nexus: Cytoscape граф ядра и служб" > qa/rework/nexus.fixed; grep -c nox-s4-lead nexus.html; grep -c nox-s4-lead finance.html
