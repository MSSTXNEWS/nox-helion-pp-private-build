#!/bin/bash
S=/workspace/nox/web/site
cd $S
echo "== nav.json"; head -c 600 nav.json; echo; /workspace/nox/venv/bin/python - <<'P'
import json
d=json.load(open('/workspace/nox/web/site/nav.json'))
print(type(d), list(d.keys()) if isinstance(d,dict) else len(d))
def walk(x,dep=0):
    if isinstance(x,list):
        for i in x: walk(i,dep)
    elif isinstance(x,dict):
        print(' '*dep, {k:(v if not isinstance(v,(list,dict)) else '...') for k,v in x.items()})
        for k,v in x.items():
            if isinstance(v,(list,dict)): print(' '*dep,'>',k); walk(v,dep+2)
walk(d)
P
echo "== html"; ls *.html | tr '\n' ' '; echo
echo "== js/css nox-*"; ls -la nox-*.js nox-*.css 2>/dev/null | awk '{print $5,$9}' | tr '\n' ';'
echo; echo "== qa"; ls qa | head -30; ls qa/rework | head -50
echo "== pult in html count"; grep -l nox-pult.js *.html | wc -l; grep -l nox-sun-x.js *.html | wc -l
echo "== api cmd"; grep -n "api/cmd\|/api/chat/stop\|/api/chat/health\|api/sleep\|api/priority\|api/wake" /workspace/nox/web/pkg/server/web_server.py | head -20
ls /workspace/nox/web/pkg/server/ | head; ls /workspace/nox/*.py | head -20
curl -s localhost:8091/web/data/live.json | head -c 400; echo
grep -o 'ninja[^;]\{0,80\}' nox-ninja.js | head -5; wc -l nox-ninja.js nox-pult.js nox-dock-pop.js settings.html nox-settings-tabs.js
echo "== dock"; grep -n "href\|label" nox-dock-pop.js | head -60
