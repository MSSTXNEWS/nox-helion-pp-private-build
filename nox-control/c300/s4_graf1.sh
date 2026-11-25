echo S4RUN:s4_graf1
S=/workspace/nox/web/site; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/s4_src
cd $S
for f in nox-s4-projects.js nox-s4-projects.css nox-s4-grafana.js; do curl -fsSL $R/$f -o $f || exit 1; done
for p in dispatcher system; do cp -n $p.html $p.html.bak_s4_1; grep -q nox-s4-grafana $p.html || python3 - $p <<'P'
import sys;p='/workspace/nox/web/site/%s.html'%sys.argv[1];t=open(p).read()
t=t.replace('</head>','<link rel="stylesheet" href="./nox-s4-projects.css"></head>',1)
if 'echarts.min.js' not in t: t=t.replace('</body>','<script src="./vendor/nox-extra/echarts.min.js"></script>\n</body>',1)
t=t.replace('</body>','<script src="./nox-s4-grafana.js" defer></script>\n</body>',1)
open(p,'w').write(t)
P
echo "S4 $p: Grafana-панели ECharts" > qa/rework/$p.fixed; done
curl -s -m5 127.0.0.1:8091/api/pc-metrics | head -c 500
