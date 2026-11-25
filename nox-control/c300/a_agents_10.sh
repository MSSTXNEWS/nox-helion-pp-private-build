W=/workspace/nox; A=$W/agents; ST=$W/state; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300
for f in nox_agents.py; do curl -fsSL --retry 5 "$R/$f?$(date +%s)" -o $A/$f.new && { cp $A/$f $A/$f.bak_a_$(date +%H%M); mv $A/$f.new $A/$f; } || echo FAIL $f; done
curl -fsSL --retry 5 "$R/agent_roles.json?$(date +%s)" -o $ST/agent_roles.json.new && { cp $ST/agent_roles.json $ST/agent_roles.json.bak_a_$(date +%H%M); mv $ST/agent_roles.json.new $ST/agent_roles.json; }
curl -fsSL --retry 5 "$R/golden_intents.json?$(date +%s)" -o $A/golden_intents.json
$A/venv/bin/python -c "import ast;ast.parse(open('$A/nox_agents.py').read());print('syntax ok')"
pkill -f agents/nox_agents.py; sleep 3
cd $A && nohup setsid $A/venv/bin/python nox_agents.py </dev/null >>service.log 2>&1 &
sleep 8; curl -s -m 5 127.0.0.1:8810/health; echo
(curl -s -m 600 127.0.0.1:8810/intents/eval > $A/intents_eval.json 2>&1 &)
echo "== site svc routes"; for u in 8080 1111 8094 8095 8092 8093 8097; do echo "$u $(curl -s -m 4 -o /dev/null -w %{http_code} 127.0.0.1:$u/svc/agents/) $(curl -s -m 4 -o /dev/null -w %{http_code} 127.0.0.1:$u/svc/agents/metrics)"; done
grep -n "svc_registry" $W/web/pkg/server/*.py | head -5 | cut -c1-160
echo "== workers (черви) и dream"; ls $W/state/mind | head; head -c 400 $W/state/mind/dreamer.json; echo; tail -c 500 $W/state/mind/dream.jsonl; echo
ps -eo pid,etimes,args | grep -E 'dream|mind|worm|nexus' | grep -v grep | cut -c1-200 | head
grep -rliE 'worm|черв' $W/svc $W/agent $W/router $W/operators $W/living 2>/dev/null | head -12
ls $W/state | grep -iE 'hunger|quota|catalog|genesis|ledger|s03|err' | head
