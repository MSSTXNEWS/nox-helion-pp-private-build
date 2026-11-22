#!/bin/bash
# c201: статус этапа 0 (только чтение + пробы чата)
R=/root/nox
echo "== NOXHF marks"; grep -c NOXHF $R/web_server.py $R/repo/nox-control/glm53/qs6_core.py $R/repo/nox-control/qs6/memory_layer.py 2>&1
echo "== service strings"; grep -n "готовлю в фоне\|Быстрый слой ответил пусто" $R/web_server.py $R/repo/nox-control/glm53/*.py $R/web/*.js 2>/dev/null | cut -c1-150 | head
echo "== ports"; for p in 8081 8082 8083 8090 8091 8095; do printf "$p:%s " $(curl -s -m3 -o /dev/null -w %{http_code} http://127.0.0.1:$p/health); done; echo
echo "== procs"; ps -eo pid,etimes,args | grep -E "gateway|web_server|nox_core|llama-server" | grep -v grep | cut -c1-150
echo "== boot flags"; grep -n "NOX_\(CORE\|PRIME\|UPSTREAM\|FAST\)" $R/boot_s1.sh | cut -c1-160 | head; ls $R/src/wow7 $R/src/BRAIN 2>&1 | head -3
echo "== repo"; git -C $R/repo status --short | head -5; git -C $R/repo log --oneline -1
ask(){ curl -sN -m90 http://127.0.0.1:8091/api/chat -H 'Content-Type: application/json' -d "{\"messages\":[{\"role\":\"user\",\"content\":\"$1\"}],\"stream\":true}" | python3 -c "
import sys,json
t='';ph=[]
for l in sys.stdin:
    try: o=json.loads(l)
    except Exception: continue
    m=o.get('message') or {}
    t+=m.get('content','')
    if o.get('nox_phase') or m.get('nox_phase'): ph.append(str(o.get('nox_phase') or m.get('nox_phase'))[:40])
    if o.get('error'): t+='[ERR '+str(o['error'])[:80]+']'
print(repr(t[:260]),ph[:2])"; }
for q in "привет" "привет" "привет" "как сервер?" "удали прошлые запросы"; do echo "Q:$q -> $(ask "$q")"; done
