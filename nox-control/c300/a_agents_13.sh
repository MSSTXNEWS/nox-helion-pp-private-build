W=/workspace/nox; A=$W/agents; ST=$W/state; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300
for f in nox_agents.py nox_worms.py; do curl -fsSL --retry 5 "$R/$f?$(date +%s)" -o $A/$f.new && { [ -f $A/$f ] && cp $A/$f $A/$f.bak_a_$(date +%H%M); mv $A/$f.new $A/$f; } || echo FAIL $f; done
$A/venv/bin/python -c "import ast;[ast.parse(open('$A/'+f).read()) for f in ('nox_agents.py','nox_worms.py')];print('syntax ok')"
pkill -f 'python nox_agents.py'; pkill -f 'agents/nox_agents.py'; sleep 3; cd $A && nohup setsid $A/venv/bin/python nox_agents.py </dev/null >>service.log 2>&1 &
sleep 10; curl -s -m 5 127.0.0.1:8810/health; echo; tail -3 $A/service.log | cut -c1-200
echo "== scan (HF/GitHub/RSS, судья)"; (curl -s -m 280 -X POST 127.0.0.1:8810/worms/scan > $A/scan_out.json &) ; sleep 100; cat $A/scan_out.json; echo
curl -s -m 10 127.0.0.1:8810/worms | python3 -c "import json,sys;d=json.load(sys.stdin);print('голод',d['hunger'],d['phrase']);[print(' ',f['src'],f['name'],f['license'][:30],f['score'],f['status']) for f in d['finds'][:14]]"
curl -s -m 10 127.0.0.1:8810/worms/cards | python3 -c "import json,sys;d=json.load(sys.stdin);print('карточки охоты',len(d['hunt']),[c['text'][:70] for c in d['hunt'][:3]]);print('самоулучшение',[c['text'][:100] for c in d['self'][:3]])"
echo "== STOP за 10 с"; curl -s -X POST 127.0.0.1:8810/worms/stop; sleep 1; curl -s 127.0.0.1:8810/worms | python3 -c "import json,sys;print('stopped',json.load(sys.stdin)['stopped'])"; curl -s -X POST 127.0.0.1:8810/worms/start
echo; cat $A/intents_eval.json | head -c 600; echo
curl -s 127.0.0.1:8810/golden/result | python3 -c "import json,sys;d=json.load(sys.stdin);print('GOLDEN',d['accepted'],'/',d['n'],[t['status'][:4] for t in d['tasks']])"
cat $A/worms.err 2>/dev/null | tail -3
