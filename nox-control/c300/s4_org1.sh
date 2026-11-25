echo S4RUN:s4_org1
S=/workspace/nox/web/site; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/s4_src
cd $S; for f in nox-s4-organs.js nox-s4-brain.css nox-s4-training.js nox-s4-training.css nox-s4-grafana.js nox-s4-projects.css nox-s4-cal.css nox-s4-memory.css; do curl -fsSL "$R/$f?t=$(date +%s)" -o $f || exit 1; done
cp -n organism.html organism.html.bak_s4_3
grep -q nox-s4-organs organism.html || python3 - <<'P'
p='/workspace/nox/web/site/organism.html';t=open(p).read()
t=t.replace('</head>','<link rel="stylesheet" href="./vendor/nox-x/tabulator/tabulator_midnight.min.css"><script src="./vendor/nox-x/tabulator/tabulator.min.js"></script></head>',1)
t=t.replace('</body>','<script src="./nox-s4-organs.js" defer></script>\n</body>',1)
open(p,'w').write(t)
P
grep -c nox-s4-organs organism.html
# 3d-force-graph на consciousness: после consc() добавить граф ядер
cp -n nox-brain-x.js nox-brain-x.js.bak_s4_4
python3 - <<'P'
p='/workspace/nox/web/site/nox-brain-x.js';t=open(p).read()
if 'S4CG' not in t:
    old="consc: () => consc(),"
    assert old in t
    t=t.replace(old,"consc: async () => { await consc(); await coreGraph(undefined, false); /*S4CG*/ },",1); open(p,'w').write(t)
P
grep -c S4CG nox-brain-x.js
