S=/workspace/nox/web/site
cd $S
[ -f x.txt ] && cp -p x.txt x.txt.bak_s1_$(date +%H%M%S)
base64 -d > x.txt <<'S1EOF'
eAo=
S1EOF
echo OK x.txt $(wc -c <x.txt)
cd /workspace/nox/web/site
grep -o "NOXcmd([^)]*)" nox-pult.js nox-chat-tg.js nox-actions.js | sort -u | head -14
python3 - <<'P'
import json
c=json.load(open('qa/registry.json'))['commands']
for k in ['depth','volume','focus','projector','voice','svc.status','health','search.meili','training.apply','persona.get','cal.list']: print(k, json.dumps(c[k],ensure_ascii=False)[:260])
P
grep -c "tgs" nox-chat-tg.css; grep -o "\-\-tgs:[^;]*" nox-chat-tg.css | head -4
grep -o "grid-column:[^;]*;grid-row:[^;}]*" nox-chat-tg.css | sort | uniq -c | head -12
