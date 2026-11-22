#!/bin/bash
# stage2: применить хотфикс на прод :8091 с бэкапом .bak_hotfix, авто-откат при провале проверки
cd /root/nox; W=/root/nox/web_server.py; TS=$(date +%Y%m%d%H%M%S)
H="Accept: application/vnd.github.raw"; A=https://api.github.com/repos/MSSTXNEWS/nox-helion-pp-private-build/contents/nox-control/web
curl -fsSL -H "$H" "$A/wow7/hf_patch_web.py?ref=main" -o /tmp/hf_patch_web.py && curl -fsSL -H "$H" "$A/restart.py?ref=main" -o /tmp/hf_restart.py || { echo fetch fail; exit 1; }
cp -a $W $W.bak_hotfix_$TS
python3 -I /tmp/hf_patch_web.py $W /tmp/ws_new.py || exit 1
python3 -I -m py_compile /tmp/ws_new.py || exit 1
cp /tmp/hf_restart.py /root/nox/hf_restart.py
cat > /root/nox/hotfix_rollback.sh <<R
#!/bin/bash
# откат хотфикса чата NOX: вернуть web_server.py и перезапустить :8091
cp -a $W.bak_hotfix_$TS $W && python3 /root/nox/hf_restart.py 8091 /root/nox/logs/web_server.log && sleep 3 && curl -s -m5 -o /dev/null -w "web %{http_code}\n" http://127.0.0.1:8091/web/chat.html
R
chmod +x /root/nox/hotfix_rollback.sh
cp /tmp/ws_new.py $W
python3 /root/nox/hf_restart.py 8091 /root/nox/logs/web_server.log; sleep 4
code=$(curl -s -m8 -o /dev/null -w "%{http_code}" http://127.0.0.1:8091/web/chat.html); echo "after restart: $code"
if [ "$code" != "200" ]; then echo ROLLBACK; bash /root/nox/hotfix_rollback.sh; exit 1; fi
ask(){ curl -sN -m90 http://127.0.0.1:8091/api/chat -H 'Content-Type: application/json' -d "{\"messages\":[{\"role\":\"user\",\"content\":\"$1\"}],\"stream\":true,\"nox_mode\":\"fast\"}" | python3 -c "
import sys,json
t='';ph=[]
for l in sys.stdin:
    try: o=json.loads(l)
    except Exception: continue
    m=o.get('message') or {}
    t+=m.get('content','')
    if o.get('nox_phase') or m.get('nox_phase'): ph.append('phase')
    if o.get('error'): t+='[ERR '+str(o['error'])[:80]+']'
print(repr(t[:320]),ph)"; }
for q in "привет" "привет" "привет" "как сервер?" "удали прошлые запросы"; do echo "Q:$q -> $(ask "$q")"; done
echo "rollback: bash /root/nox/hotfix_rollback.sh (backup $W.bak_hotfix_$TS)"
