echo "C300: u_rec6"
S=/workspace/nox/web/site; cd $S
python3 - <<'PYX'
import json
a=json.load(open('qa/audit.json',encoding='utf-8'))
for p in ('creative','settings'):
    d=a.get(p) or {}
    print('==',p,type(d).__name__,list(d)[:12])
    s=json.dumps(d,ensure_ascii=False)
    import re
    # печатаем всё кроме больших base64/логов
    print(s[:3800])
PYX
echo "== rework json"; head -c 1500 qa/rework/creative.json; echo; head -c 1500 qa/rework/settings.json; echo
echo "== 404/errors creative"; curl -s -m 5 -o /dev/null -w "%{http_code}\n" localhost:8091/web/creative.html
