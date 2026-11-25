echo "C300: a2_gw5 (восстановление MOCKQA/P3_PRIVATE + квоты чата)"
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build; G=/workspace/nox/advisors; A=/workspace/nox/agents
curl -fsSL "$R/7628731e6818a65feb3da9b38001818150ca5809/nox-control/c300/v_gw_gateway.py" -o /tmp/gw_base.py; curl -fsSL "$R/5aa50b2e8e5d992bacd3c9040a88bac0cc989acf/nox-control/c300/v_gw_gateway.py" -o /tmp/gw_mine.py
diff -u /tmp/gw_base.py /tmp/gw_mine.py > /tmp/quota.diff; wc -l /tmp/quota.diff
cp $G/gateway.py.bak_a2_gw3 /tmp/gw_theirs.py
grep -c "MOCKQA" /tmp/gw_theirs.py; grep -c "P3_PRIVATE" /tmp/gw_theirs.py
cp /tmp/gw_theirs.py /tmp/gw_merged.py; patch -s /tmp/gw_merged.py < /tmp/quota.diff; rm -f /tmp/gw_merged.py.rej /tmp/gw_merged.py.orig; echo PATCH_DONE
curl -fsSL "$R/c6593acf771f3f1cb81c99e5b27478c51c7d5dfa/nox-control/c300/a2_gw_merge.py" -o /tmp/a2_gw_merge.py; python3 /tmp/a2_gw_merge.py; python3 -c "import ast;ast.parse(open('/tmp/gw_merged.py').read())" && echo SYNTAX_OK
echo "markers:" $(grep -c "MOCKQA" /tmp/gw_merged.py) $(grep -c "P3_PRIVATE" /tmp/gw_merged.py) $(grep -c "chat_metric" /tmp/gw_merged.py) $(grep -c "RESERVE" /tmp/gw_merged.py)
if grep -q SYNTAX_OK /dev/null; then :; fi
python3 -c "import ast;ast.parse(open('/tmp/gw_merged.py').read())" && [ "$(grep -c MOCKQA /tmp/gw_merged.py)" -ge 2 ] && [ "$(grep -c P3_PRIVATE /tmp/gw_merged.py)" -ge 1 ] && [ "$(grep -c chat_metric /tmp/gw_merged.py)" -ge 2 ] && {
  cp $G/gateway.py $G/gateway.py.bak_a2_gw5; cp /tmp/gw_merged.py $G/gateway.py; echo INSTALLED
  pkill -f advisors/gateway.py; sleep 1
  setsid -f nohup python3 $G/gateway.py >/workspace/nox/svc/logs/advisors.log 2>&1 </dev/null
  sleep 3; curl -s -m5 127.0.0.1:8793/health | head -c 50; echo
} || echo "НЕ УСТАНОВЛЕНО: маркеры/синтаксис"
echo "== проверки"
MQ=$(ls /workspace/nox/state/mock_qa/*.jpg /workspace/nox/state/mock_qa/*.png 2>/dev/null | head -1); echo "mock_qa файл: $MQ"
J(){ curl -s -m "$1" -o /tmp/o.json -w "%{http_code}" "${@:2}"; echo " $(head -c 160 /tmp/o.json | tr '\n' ' ')"; }
[ -n "$MQ" ] && { echo -n "mock_qa+allow -> "; J 100 -X POST 127.0.0.1:8793/v1/images/critique -H 'Content-Type: application/json' -d "{\"image_path\":\"$MQ\",\"prompt\":\"проверка\",\"x_nox_allow_image\":true}"; echo -n "mock_qa без allow -> "; J 20 -X POST 127.0.0.1:8793/v1/images/critique -H 'Content-Type: application/json' -d "{\"image_path\":\"$MQ\",\"prompt\":\"проверка\"}"; }
echo -n "живой путь /etc/passwd -> "; J 20 -X POST 127.0.0.1:8793/v1/images/critique -H 'Content-Type: application/json' -d '{"image_path":"/etc/passwd","prompt":"x","x_nox_allow_image":true}'
echo -n "фото владельца b64 -> "; J 20 -X POST 127.0.0.1:8793/v1/images/critique -H 'Content-Type: application/json' -d "{\"image_b64\":\"$(head -c 3000 /dev/zero | base64 -w0)\",\"prompt\":\"x\"}"
echo -n "приватная тема -> "; J 20 -X POST 127.0.0.1:8793/v1/chat/completions -H 'Content-Type: application/json' -d '{"model":"auto","messages":[{"role":"user","content":"помоги с иском о сносе дома в суде"}],"max_tokens":10}'
echo -n "обычный чат prio9 no_cache -> "; J 60 -X POST 127.0.0.1:8793/v1/chat/completions -H 'Content-Type: application/json' -d '{"model":"auto","messages":[{"role":"user","content":"скажи ок"}],"max_tokens":10,"x_nox_prio":9,"no_cache":true}'
curl -s -m5 127.0.0.1:8793/v1/chat_metric; echo
cat > /tmp/a2_chatload.py <<'P'
import json,time,urllib.request,concurrent.futures as cf,collections
def req(i,prio,tag):
    t=time.time()
    try:
        r=urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8793/v1/chat/completions',data=json.dumps({'model':'auto','messages':[{'role':'user','content':f'[{tag}{i}] Назови {i%7+3} цветов через запятую.'}],'max_tokens':40,'x_nox_prio':prio,'no_cache':prio>=9}).encode(),headers={'Content-Type':'application/json'}),timeout=90)
        j=json.loads(r.read()); return tag,200,(j.get('nox') or {}).get('provider',''),time.time()-t
    except urllib.error.HTTPError as e: return tag,e.code,'',time.time()-t
    except Exception as e: return tag,0,type(e).__name__,time.time()-t
jobs=[(i,5,'task') for i in range(40)]+[(i,9,'chat') for i in range(20)]
import random; random.seed(1); random.shuffle(jobs)
t0=time.time()
with cf.ThreadPoolExecutor(8) as ex: res=list(ex.map(lambda a:req(*a),jobs))
for tag in ('task','chat'):
    r=[x for x in res if x[0]==tag]; ok=sum(1 for x in r if x[1]==200); print(tag,'n',len(r),'ok',ok,round(100*ok/len(r)),'%','провайдеры',dict(collections.Counter(x[2] for x in r if x[1]==200)),'медиана',round(sorted(x[3] for x in r)[len(r)//2],1),'с','коды',dict(collections.Counter(x[1] for x in r)))
print('сек',round(time.time()-t0))
P
setsid -f sh -c "python3 /tmp/a2_chatload.py > /workspace/nox/agents/chatload.log 2>&1" </dev/null >/dev/null 2>&1
echo started load
