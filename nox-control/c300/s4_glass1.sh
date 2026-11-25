echo S4RUN:s4_glass1
S=/workspace/nox/web/site; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/s4_src
cd $S; for f in nox-s4-glass.css nox-s4-glass.js nox-s4-training.js nox-s4-cal.js; do curl -fsSL "$R/$f?t=$(date +%s)" -o $f || exit 1; done
cp -n nox-brain-x.js nox-brain-x.js.bak_s4_1
python3 - <<'P'
p='/workspace/nox/web/site/nox-brain-x.js';t=open(p).read()
if 'S4SLIDER' not in t:
    t=t.replace("type: 'slider', height: 22,","type: 'slider', /*S4SLIDER*/ height: 22, backgroundColor: 'rgba(255,235,220,.04)', dataBackground: { lineStyle: { color: 'rgba(255,130,80,.35)' }, areaStyle: { color: 'rgba(255,130,80,.10)' } }, selectedDataBackground: { lineStyle: { color: '#e0654a' }, areaStyle: { color: 'rgba(224,101,74,.25)' } }, handleStyle: { color: '#e0654a', borderColor: '#e0654a' }, moveHandleStyle: { color: 'rgba(224,101,74,.5)' }, brushSelect: false,")
    open(p,'w').write(t)
P
for p in system selffeel soul consciousness organism growth training dispatcher projects calendar downloads memory; do
  [ -f $p.html ] || continue; cp -n $p.html $p.html.bak_s4_1
  grep -q nox-s4-glass.css $p.html || sed -i 's|</head>|<link rel="stylesheet" href="./nox-s4-glass.css"></head>|' $p.html
  if [ $p = system ]; then grep -q nox-s4-glass.js $p.html || sed -i 's|</body>|<script src="./nox-s4-glass.js" defer></script>\n</body>|' $p.html; fi
  echo $p $(grep -c nox-s4-glass $p.html)
done
grep -c S4SLIDER nox-brain-x.js
