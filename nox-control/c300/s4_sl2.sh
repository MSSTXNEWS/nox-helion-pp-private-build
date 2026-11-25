echo S4RUN:s4_sl2
cd /workspace/nox/web/site; cp -n nox-brain-x.js nox-brain-x.js.bak_s4_5
python3 - <<'P'
import re
p='/workspace/nox/web/site/nox-brain-x.js';t=open(p).read()
sty=" backgroundColor: 'rgba(255,235,220,.04)', borderColor: 'rgba(255,225,200,.14)', fillerColor: 'rgba(224,101,74,.22)', dataBackground: { lineStyle: { color: 'rgba(255,130,80,.35)' }, areaStyle: { color: 'rgba(255,130,80,.10)' } }, selectedDataBackground: { lineStyle: { color: '#e0654a' }, areaStyle: { color: 'rgba(224,101,74,.25)' } }, handleStyle: { color: '#e0654a', borderColor: '#e0654a' }, moveHandleStyle: { color: 'rgba(224,101,74,.5)' }, textStyle: { color: '#9a8f88' }, brushSelect: false,"
n=0
def r(m):
    global n; n+=1; return "{ type: 'slider', /*S4SL2*/ height: %s, bottom: %s,%s"%(m.group(1),m.group(2),sty)
t2=re.sub(r"\{ type: 'slider', height: (\d+), bottom: (\d+)(?=[ ,}])",lambda m: r(m)+" ",t) if 'S4SL2' not in t else t
open(p,'w').write(t2); print('patched',n)
P
grep -c "S4SL2" nox-brain-x.js
grep -n "S4SL2" nox-brain-x.js | cut -c1-90
