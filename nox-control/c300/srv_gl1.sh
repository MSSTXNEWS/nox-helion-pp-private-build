#!/bin/bash
cat > /tmp/srv_gl.py <<'PYEOF'
import sys,shutil,time,py_compile
G="/workspace/nox/advisors/gateway.py"; s=open(G,encoding="utf-8").read()
if "LITELLM_P3" in s: print("already"); sys.exit(0)
shutil.copy(G,G+".bak_litellm_%d"%int(time.time()))
a="def call(p, model, body, timeout):"; assert s.count(a)==1
new='''def _call_raw(p, model, body, timeout):'''
s=s.replace(a,new,1)
b="def models_of(p):"; assert s.count(b)==1
adapter='''# LITELLM_P3 (этап 1): вызов провайдера через litellm.completion (единые ошибки, Retry-After, usage-журнал). Квоты/резерв/приватность/MOCKQA остаются в шлюзе.
# Выключатель без рестарта: touch state/gw_litellm.off. Откат: gateway.py.bak_litellm_*.
_LL = {"mod": None, "tried": False}
def _ll():
    if not _LL["tried"]:
        _LL["tried"] = True
        try:
            import litellm
            litellm.drop_params = True; litellm.telemetry = False; litellm.suppress_debug_info = True
            def _usage(kw, resp, t0, t1):
                try:
                    u = getattr(resp, 'usage', None); os.makedirs(ST + '/gw_journal', exist_ok=True)
                    rec = {'ts': time.strftime('%Y-%m-%dT%H:%M:%S'), 'kind': 'usage', 'base': str(kw.get('api_base', ''))[-30:], 'model': str(kw.get('model', ''))[:60],
                           'pt': getattr(u, 'prompt_tokens', None), 'ct': getattr(u, 'completion_tokens', None), 'ms': int((t1 - t0).total_seconds() * 1000)}
                    open(ST + '/gw_journal/usage-' + time.strftime('%Y-%m-%d') + '.jsonl', 'a').write(json.dumps(rec) + '\\n')
                except Exception: pass
            litellm.success_callback = [_usage]
            _LL["mod"] = litellm
        except Exception: _LL["mod"] = None
    return _LL["mod"]
def call(p, model, body, timeout):
    if os.path.exists(ST + '/gw_litellm.off'): return _call_raw(p, model, body, timeout)
    ll = _ll()
    if ll is None: return _call_raw(p, model, body, timeout)
    pr = PROV[p]
    kw = dict(model='openai/' + model, api_base=pr['base'], api_key=(None if pr.get('keyless') else key_of(p)) or 'x', messages=body.get('messages'),
              timeout=max(timeout, pr.get('timeout', 0)), num_retries=0)
    for k in ('max_tokens', 'temperature'):
        if k in body: kw[k] = body[k]
    try:
        r = ll.completion(**kw)
        return r.model_dump()
    except Exception as e:
        code = getattr(e, 'status_code', None)
        if isinstance(code, int) and code >= 400:
            import http.client as _hc
            h = _hc.HTTPMessage()
            try:
                ra = (getattr(getattr(e, 'response', None), 'headers', None) or {}).get('retry-after')
                if ra: h['Retry-After'] = str(ra)
            except Exception: pass
            raise urllib.error.HTTPError(pr['base'], code, str(e)[:200], h, None)
        raise
'''
s=s.replace(b,adapter+b,1)
open(G,"w",encoding="utf-8").write(s); py_compile.compile(G,doraise=True); print("patched")
PYEOF
N=/workspace/nox; G=$N/advisors/gateway.py
python3 -I /tmp/srv_gl.py || exit 1
OLD=$(pgrep -f 'advisors/gateway.py' | head -1); tr '\0' '\n' </proc/$OLD/environ > /tmp/gw_env.txt
kill $OLD; sleep 1
python3 -I - <<'PY'
import subprocess
env=dict(l.split("=",1) for l in open("/tmp/gw_env.txt").read().splitlines() if "=" in l)
subprocess.Popen(["/workspace/nox/venv/bin/python","/workspace/nox/advisors/gateway.py"],env=env,cwd="/workspace/nox/advisors",stdout=open("/workspace/nox/state/gw_restart.log","a"),stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,start_new_session=True)
PY
rm -f /tmp/gw_env.txt; sleep 6
curl -s -m5 127.0.0.1:8793/health | head -c 80; echo
if ! curl -s -m5 127.0.0.1:8793/health >/dev/null; then cp $(ls -t $G.bak_litellm_* | head -1) $G; setsid -f python3 $G >> $N/state/gw_restart.log 2>&1 < /dev/null; echo ROLLED_BACK; fi
for q in "Сколько будет 3+4?" "Назови столицу Франции."; do curl -s -m60 -X POST 127.0.0.1:8793/v1/chat/completions -H 'Content-Type: application/json' -d "{\"model\":\"auto\",\"messages\":[{\"role\":\"user\",\"content\":\"$q\"}],\"max_tokens\":30,\"x_nox_prio\":3,\"no_cache\":true}" | python3 -c "import sys,json;d=json.load(sys.stdin);print(d.get('model'),(d.get('choices') or [{}])[0].get('message',{}).get('content','')[:40],d.get('nox',{}).get('tried'),d.get('error'))"; done
tail -4 $N/state/gw_journal/usage-*.jsonl 2>/dev/null | tail -3; tail -3 $N/state/gw_restart.log | cut -c1-160; ps -o etimes=,args= -p $(pgrep -f advisors/gateway.py | head -1) | cut -c1-80
