echo "== guard"; cat /workspace/nox/ops/chat_priority_guard.sh | head -70; pgrep -af chat_priority_guard | cut -c1-150
echo "== health full"; curl -s -m 4 127.0.0.1:8091/api/nox/status | head -c 2500; echo; curl -s -m 4 127.0.0.1:8090/health | head -c 800; echo
for u in /api/chat/active /api/chat/turns /api/nox/active /svc/ /api/pc-metrics; do echo "$u $(curl -s -m 4 -w ' [%{http_code}]' 127.0.0.1:8091$u | head -c 300)"; done
echo "== state"; ls /workspace/nox/state | head -40; cat /workspace/nox/state/arbiter.json 2>&1 | head -c 400
echo "== train dirs"; ls /workspace/nox/distill_v2/ckpt | tail -5; ls /workspace/nox/ops | grep -E "^v5_" | head; ls /workspace/nox/agent/autotrain | head
echo "== registry"; python3 - <<'P'
import json;r=json.load(open('/workspace/nox/site/qa/registry.json'))
print(type(r).__name__, list(r)[:10] if isinstance(r,dict) else len(r))
def f(o,d=0):
    if isinstance(o,dict):
        for k,v in list(o.items())[:4]:
            print(' '*d,k,type(v).__name__, (json.dumps(v,ensure_ascii=False)[:260] if not isinstance(v,(dict,list)) or d>0 else ''))
            if d<1: f(v,d+1)
    elif isinstance(o,list): print(' '*d,'list',len(o),json.dumps(o[:2],ensure_ascii=False)[:500])
f(r)
P
ls /workspace/nox/site/qa | head; grep -rn "chat_active\|active_turns" /workspace/nox/web/pkg --include=*.py -l 2>/dev/null | head -5
tail -3 /workspace/nox/svc/start_extra.sh | cut -c1-200; wc -l /workspace/nox/svc/start_extra.sh
