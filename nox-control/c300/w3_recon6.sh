S=/workspace/nox/web/site; cd $S
sed -n '236,262p' nox-wow.js | cut -c1-700
echo ==EVENTS; grep -o "fetch([^)]\{0,100\}" events.html nox-p-*.js 2>/dev/null | grep -i event | head; ls | grep -i event
python3 - <<'P'
import json,urllib.request
def walk(o,p="",d=0):
    if isinstance(o,dict) and d<4:
        for k,v in o.items(): walk(v,p+"/"+k,d+1)
    else:
        s=json.dumps(o,ensure_ascii=False); print(p,s[:90])
d=json.load(urllib.request.urlopen("http://127.0.0.1:8091/glm/v1/nox/stats",timeout=20)); walk(d)
P
grep -n "tour\|driver" nox-wow.js | cut -c1-200 | head -12
grep -n "\.acts" nox-wow.css nox-unify.css | cut -c1-260 | head
