echo "C300: v_diag_3"
R=/workspace/nox/router
ls $R $R/router | head -40
python3 - <<'P'
import json
c=json.load(open('/workspace/nox/router/router/catalog.json'))
print(type(c), list(c)[:8] if isinstance(c,dict) else len(c))
items=c.get('advisors',c) if isinstance(c,dict) else c
print(json.dumps(items,ensure_ascii=False)[:3500])
P
echo --- health; head -c 3500 /workspace/nox/agent/out/ADVISORS_HEALTH.json
echo --- cfg; grep -n "model_name\|api_base\|port" $R/config.yaml | head -50
echo --- shim health; curl -s -m5 127.0.0.1:4210/health | head -c 1500; echo
curl -s -m5 127.0.0.1:4220/health | head -c 1200; echo
ss -ltnp | grep -E ":4000|:4100|:4210|:4220" | awk '{print $4}'
