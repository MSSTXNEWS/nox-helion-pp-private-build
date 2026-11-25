R=$(ls /workspace/nox/web/site/qa/registry.json /workspace/nox/web/site/qa/*.json 2>&1 | head -8); echo "$R"
python3 - <<'P'
import json
r=json.load(open('/workspace/nox/web/site/qa/registry.json'))
print(type(r).__name__, list(r)[:12] if isinstance(r,dict) else len(r))
s=json.dumps(r,ensure_ascii=False)
print(len(s)); 
i=s.find('status'); print(s[:700]); print('...'); print(s[max(0,i-300):i+400])
P
grep -rln "registry.json" /workspace/nox/web/pkg /workspace/nox/tools /workspace/nox/svc 2>/dev/null | head -5
curl -s -m4 127.0.0.1:8090/health | python3 -c "import sys,json;d=json.load(sys.stdin);print({k:d[k] for k in d if k in('running','turns','glm','bg')})" | cut -c1-500
ls -la --time-style=full-iso /workspace/nox/state/orch/ | head; 
