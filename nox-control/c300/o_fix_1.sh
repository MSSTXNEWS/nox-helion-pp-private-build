NOX=/workspace/nox; F=$NOX/web/site/qa/registry.json
B=$(ls -t $F.bak_o_* | tail -1); echo "oldest bak $B"; python3 -c "import json;json.load(open('$B'));print('bak valid')" && cp $F $F.bak_o_bad_$(date +%H%M%S) && cp $B $F && echo restored
python3 - <<'P'
import json
r=json.load(open('/workspace/nox/web/site/qa/registry.json'))
c=r['commands']; print('commands',type(c).__name__,len(c)); print(json.dumps(c if isinstance(c,dict) else c[:3],ensure_ascii=False)[:1200])
print(json.dumps(r['sections'],ensure_ascii=False)[:300])
P
echo "== chat_hold"; ls -la --time-style=full-iso $NOX/state/orch/chat_hold; date; ls $NOX/state/orch | head; cat $NOX/state/orch/guard.pid; tail -5 $NOX/agent/out/chat_priority.log
echo "== chat api"; grep -ho "fetch([^)]*api/chat[^)]*)" $NOX/web/site/*.js 2>/dev/null | head -3; grep -ho "api/chat[^;]\{0,200\}" $NOX/web/site/chat.html | head -3
grep -n "нет сообщения пользователя" -r $NOX/web/pkg/server/*.py | head -3
sleep 20; ls -la --time-style=full-iso $NOX/state/orch/chat_hold; date; tail -3 $NOX/arbiter.log | cut -c1-120; head -c 200 $NOX/state/arbiter.json
