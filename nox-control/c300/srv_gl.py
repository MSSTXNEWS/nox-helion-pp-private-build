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
