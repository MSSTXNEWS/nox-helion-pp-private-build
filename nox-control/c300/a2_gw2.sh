echo "C300: a2_gw2"
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/7628731e6818a65feb3da9b38001818150ca5809/nox-control/c300; G=/workspace/nox/advisors; A=/workspace/nox/agents
cp $G/gateway.py $G/gateway.py.bak_a2_gw2
curl -fsSL "$R/v_gw_gateway.py" -o $G/gateway.py.new && python3 -c "import ast;ast.parse(open('$G/gateway.py.new').read())" && mv $G/gateway.py.new $G/gateway.py || echo FAIL
curl -fsSL "$R/nox_worms.py" -o $A/nox_worms.py.new && $A/venv/bin/python -c "import ast;ast.parse(open('$A/nox_worms.py.new').read())" && cp $A/nox_worms.py $A/nox_worms.py.bak_a2_gw2 && mv $A/nox_worms.py.new $A/nox_worms.py || echo FAIL worms
grep -c "локальный советник" $G/gateway.py
pkill -f advisors/gateway.py; sleep 1
setsid -f nohup python3 $G/gateway.py >/workspace/nox/svc/logs/advisors.log 2>&1 </dev/null
sleep 3; curl -s -m5 127.0.0.1:8793/health | head -c 80; echo
for m in lcoder/coder3b ltrainer/trainer17b ltlite/judge_tlite_cpu; do curl -s -m 60 127.0.0.1:8793/v1/chat/completions -H 'Content-Type: application/json' -d "{\"model\":\"$m\",\"messages\":[{\"role\":\"user\",\"content\":\"Столица Франции? Одним словом.\"}],\"max_tokens\":20,\"x_nox_local_only\":true}" | python3 -c "
import json,sys
d=json.load(sys.stdin); print('$m', d.get('choices',[{}])[0].get('message',{}).get('content','')[:40].replace('\n',' '), d.get('nox',{}).get('label'), d.get('nox',{}).get('ms'), d.get('error'))"; done
python3 - <<'P'
import json
f='/workspace/nox/state/advisors_external.json'; d=json.load(open(f))
for p,m,t in (('lcoder','coder3b','Qwen2.5-Coder-3B'),('ltrainer','trainer17b','trainer 1.7B'),('ltlite','judge_tlite_cpu','T-lite 2.1')):
    i='local_'+p
    d['advisors']=[a for a in d['advisors'] if a['id']!=i]+[{'id':i,'provider':p,'model':m,'title':t+' (локальный советник)','strengths':'запасной, быстрый, слабее внешних','status':'ok','local':True,'needs_key':False,'limits':'свободные слоты сервера'}]
json.dump(d,open(f,'w'),ensure_ascii=False,indent=1); print('registry +3 local')
P
setsid -f sh -c "python3 $A/a2_pool_measure.py 24 after > $A/measure_after.log 2>&1; python3 $A/a2_pool_measure.py 24 after2 > $A/measure_after2.log 2>&1" </dev/null >/dev/null 2>&1
sleep 120; cat $A/measure_after.log
