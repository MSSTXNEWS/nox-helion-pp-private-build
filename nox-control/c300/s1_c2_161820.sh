S=/workspace/nox/web/site
cd $S
[ -f x.txt ] && cp -p x.txt x.txt.bak_s1_$(date +%H%M%S)
base64 -d > x.txt <<'S1EOF'
eAo=
S1EOF
echo OK x.txt $(wc -c <x.txt)
cd /workspace/nox/web/site
for u in /api/pc-metrics /glm /api/autotrain /api/autotrain/status /api/cmd /api/nox-live; do echo "EP $u $(curl -s -m6 -w ' %{http_code}' http://127.0.0.1:8091$u | head -c 330)"; done
python3 - <<'P'
import json
r=json.load(open('qa/registry.json'))
print(list(r['sections'].keys())[:40])
for k,v in r['sections'].items():
    if 'cmd' in k.lower() or 'command' in k.lower(): print(k, json.dumps(v,ensure_ascii=False)[:800])
P
head -c 1500 nox-cmd.js
grep -o 'cx-right[^{]*{[^}]*}' nox-chat-tg.css | head -3 | cut -c1-250
grep -n "cx-right\|cx-side" nox-chat-tg.js | head -12 | cut -c1-200
grep -o "id=\"tgCmd\"[^>]*\|id=\"tgDepth\"[^>]*" nox-chat-tg.js | head
