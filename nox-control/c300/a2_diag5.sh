echo "C300: a2_diag5"
cat /workspace/nox/state/advisors_usage.json | head -c 600; echo
curl -s -m10 127.0.0.1:8793/v1/models | python3 -c "
import json,sys
d=json.load(sys.stdin); print([k for k in d if k!='data']); print(d.get('usage'))
print([(m['id'][:40],m['status'],m.get('latency_ms')) for m in d['data'] if m['status']=='ok'])"
grep -iE "BAD|quarantine|429|402" /workspace/nox/svc/logs/advisors.log | tail -5 | cut -c1-200
cat /workspace/nox/state/advisors_cfg.json | head -c 400
for i in 1 2 3; do curl -s -m 60 -X POST 127.0.0.1:8793/v1/chat/completions -H 'Content-Type: application/json' -d '{"model":"auto","messages":[{"role":"user","content":"скажи ок"}],"max_tokens":10}' | head -c 300; echo; done
curl -s -m 5 127.0.0.1:4210/health 2>&1 | head -c 400
