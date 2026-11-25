echo "C300: a2_gw3"
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/5aa50b2e8e5d992bacd3c9040a88bac0cc989acf/nox-control/c300; G=/workspace/nox/advisors; A=/workspace/nox/agents
echo "server gw md5 (ожидаем b37b20be...)"; md5sum $G/gateway.py
cp $G/gateway.py $G/gateway.py.bak_a2_gw3; cp $A/nox_agents.py $A/nox_agents.py.bak_a2_gw3
curl -fsSL "$R/v_gw_gateway.py" -o $G/gateway.py.new && python3 -c "import ast;ast.parse(open('$G/gateway.py.new').read())" && mv $G/gateway.py.new $G/gateway.py || echo FAIL gw
curl -fsSL "$R/nox_agents.py" -o $A/nox_agents.py.new && $A/venv/bin/python -c "import ast;ast.parse(open('$A/nox_agents.py.new').read())" && mv $A/nox_agents.py.new $A/nox_agents.py || echo FAIL agents
grep -c "chat_metric" $G/gateway.py; grep -c "NOCACHE" $A/nox_agents.py
pkill -f advisors/gateway.py; sleep 1
setsid -f nohup python3 $G/gateway.py >/workspace/nox/svc/logs/advisors.log 2>&1 </dev/null
pkill -f 'python nox_agents.py'; sleep 4; pkill -9 -f 'python nox_agents.py'; sleep 1
cd $A; setsid -f nohup $A/venv/bin/python nox_agents.py </dev/null >>service.log 2>&1
sleep 15; curl -s -m5 127.0.0.1:8793/health | head -c 60; echo
EOF_PLACEHOLDER=1
cat > /tmp/a2_chatload.py <<'P'
import json,time,urllib.request,concurrent.futures as cf,collections
def req(i,prio,tag):
    t=time.time()
    try:
        r=urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8793/v1/chat/completions',data=json.dumps({'model':'auto','messages':[{'role':'user','content':f'[{tag}{i}] Назови {i%7+3} цветов через запятую.'}],'max_tokens':40,'x_nox_prio':prio,'no_cache':prio>=9}).encode(),headers={'Content-Type':'application/json'}),timeout=90)
        j=json.loads(r.read()); return tag,200,(j.get('nox') or {}).get('provider',''),time.time()-t
    except urllib.error.HTTPError as e: return tag,e.code,'',time.time()-t
    except Exception as e: return tag,0,type(e).__name__,time.time()-t
jobs=[(i,5,'task') for i in range(40)]+[(i,9,'chat') for i in range(20)]   # фон: 40 задач prio5 параллельно с 20 запросами чата
jobs=[jobs[k//2 if k%2==0 else 40+k//2] for k in range(60)] if False else jobs
t0=time.time()
with cf.ThreadPoolExecutor(8) as ex: res=list(ex.map(lambda a:req(*a),jobs))
for tag in ('task','chat'):
    r=[x for x in res if x[0]==tag]; ok=sum(1 for x in r if x[1]==200); print(tag,'n',len(r),'ok',ok,round(100*ok/len(r)),'%','провайдеры',dict(collections.Counter(x[2] for x in r if x[1]==200)),'медиана',round(sorted(x[3] for x in r)[len(r)//2],1),'с','коды',dict(collections.Counter(x[1] for x in r)))
print('сек',round(time.time()-t0))
P
setsid -f sh -c "python3 /tmp/a2_chatload.py > /workspace/nox/agents/chatload.log 2>&1" </dev/null >/dev/null 2>&1
sleep 100; cat /workspace/nox/agents/chatload.log; curl -s -m5 127.0.0.1:8793/v1/chat_metric; echo
