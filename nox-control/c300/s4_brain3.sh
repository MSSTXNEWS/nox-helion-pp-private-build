echo S4RUN:s4_brain3
S=/workspace/nox/web/site; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/s4_src
cd $S; for f in nox-s4-brain.js nox-s4-brain.css; do curl -fsSL "$R/$f?t=$(date +%s)" -o $f || exit 1; done
for p in consciousness organism soul selffeel; do [ -f $p.html ] || continue; cp -n $p.html $p.html.bak_s4_2
 grep -q nox-s4-brain $p.html || python3 - $p <<'P'
import sys;p='/workspace/nox/web/site/%s.html'%sys.argv[1];t=open(p).read()
t=t.replace('</head>','<link rel="stylesheet" href="./nox-s4-brain.css"><script src="./vendor/paper-design-shaders/paper-design-shaders.iife.js"></script></head>',1)
t=t.replace('</body>','<script src="./nox-s4-brain.js" defer></script>\n</body>',1)
open(p,'w').write(t)
P
 echo $p $(grep -c nox-s4-brain $p.html); echo "S4 $p brain: капля Paper Shaders, Tone, тёмный llm-viz" > qa/rework/$p.fixed; done
# growth: тема ECharts для dataZoom до init
cp -n nox-brain-x.js nox-brain-x.js.bak_s4_2
python3 - <<'P'
p='/workspace/nox/web/site/nox-brain-x.js';t=open(p).read()
if 'S4THEME' not in t:
    old="const initChart = async (el, opt) => { const e = await ECH(); const c = e.init(el, null, { renderer: 'canvas' });"
    assert old in t
    new="const initChart = async (el, opt) => { const e = await ECH(); if (!e.__s4t) { /*S4THEME*/ e.registerTheme('noxglass', { dataZoom: { backgroundColor: 'rgba(255,235,220,.04)', borderColor: 'rgba(255,225,200,.14)', fillerColor: 'rgba(224,101,74,.22)', handleStyle: { color: '#e0654a', borderColor: '#e0654a' }, moveHandleStyle: { color: 'rgba(224,101,74,.5)' }, dataBackground: { lineStyle: { color: 'rgba(255,130,80,.35)' }, areaStyle: { color: 'rgba(255,130,80,.10)' } }, selectedDataBackground: { lineStyle: { color: '#e0654a' }, areaStyle: { color: 'rgba(224,101,74,.25)' } }, textStyle: { color: '#9a8f88' } } }); e.__s4t = 1; } const c = e.init(el, 'noxglass', { renderer: 'canvas' });"
    t=t.replace(old,new,1); open(p,'w').write(t)
P
grep -c S4THEME nox-brain-x.js
