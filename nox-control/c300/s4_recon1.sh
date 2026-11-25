echo S4RUN:s4_recon1
W=/workspace/nox/web; S=$W/site
echo "== disk"; df -h /workspace | tail -1
echo "== pages"; cd $S; ls -la *.html | awk '{print $5,$9}' | column -c 200
echo "== vendor"; ls $S/vendor
echo "== nm"; ls $W/build/node_modules 2>/dev/null | head -80; ls $W/build/node_modules/@* -d 2>/dev/null
echo "== nav"; python3 - <<'P'
import json;d=json.load(open('/workspace/nox/web/site/nav.json'))
def w(x,o):
    if isinstance(x,dict):
        if 'href' in x or 'url' in x: o.append((x.get('href') or x.get('url'),x.get('title') or x.get('label') or x.get('name')))
        for v in x.values(): w(v,o)
    elif isinstance(x,list):
        for v in x: w(v,o)
o=[];w(d,o);print(o)
P
echo "== progress"; tail -30 /workspace/nox/web/site/qa/PROGRESS.md 2>/dev/null || find /workspace/nox -name PROGRESS.md | head
echo "== projects.html"; head -c 1800 $S/projects.html
echo "== live.json"; head -c 1500 $S/data/live.json 2>/dev/null; ls $S/data | head -30
echo "== rework"; ls $S/qa/rework 2>/dev/null | head -30
echo "== svc"; curl -s -m5 localhost:8091/svc/ | head -c 300; curl -s -m5 localhost:8091/cal/events | head -c 300
