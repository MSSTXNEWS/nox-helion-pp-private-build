echo "C300: n_recon_4"
cd /workspace/nox/web/pkg/server
grep -n "glm" web_server.py svc_proxy.py nox_extra.py chat_core.py | head -12 | cut -c1-240
python3 - <<'P'
import json;r=json.load(open('/workspace/nox/web/site/qa/registry.json'));print(type(r).__name__, list(r)[:6] if isinstance(r,dict) else len(r))
it=r.get('commands') if isinstance(r,dict) else r
print(type(it).__name__, len(it)); 
x=it[:2] if isinstance(it,list) else list(it.items())[:2]; print(json.dumps(x,ensure_ascii=False)[:700])
P
grep -n "def _chat" -A10 web_server.py | cut -c1-200 | head -16
ls /workspace/nox/state/prompts.json 2>&1
curl -s -m 5 127.0.0.1:8091/api/identity 2>&1 | head -c 100; echo
