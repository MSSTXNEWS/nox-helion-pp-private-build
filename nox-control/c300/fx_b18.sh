S=/workspace/nox/web/site; P=/workspace/nox/web/pkg/server; T=bak_fx_b18
[ -f $P/web_server.py.$T ] || cp $P/web_server.py $P/web_server.py.$T
/workspace/nox/venv/bin/python - <<'PYEOF'
P='/workspace/nox/web/pkg/server'
w=P+'/web_server.py'; t=open(w,encoding='utf-8').read()
a='        return self._proxy(method, path, raw, MEM, "память (recall_api %s)" % MEM)'
if a in t and 'не запущен: %s' not in t:
    t=t.replace(a,'''        import socket as _s
        try: _s.create_connection((MEM.split(":")[0], int(MEM.split(":")[1])), 1.5).close()
        except Exception as e: return self._j(200, {"ok": False, "up": False, "error": "recall_api (%s) не запущен: %s" % (MEM, e)})
'''+a,1); print('mem')
a='        if p == "/api/status": return self._j(200,'
if a in t and '/api/nox/status' not in t:
    t=t.replace(a,'        if p == "/api/nox/status": return self._glm_compat("/glm/v1/nox/stats")\n        if p == "/glm/props": return self._j(200, {"ok": False, "note": "параметры llama-server доступны только у загруженной модели (llama-swap :8200 подгружает по запросу)"})\n'+a,1); print('status/props')
else: print('miss', a in t)
open(w,'w',encoding='utf-8').write(t)
PYEOF
grep -n '"/glm/props"\|/api/nox/status' $P/web_server.py | cut -c1-80
grep -n 'p.startswith("/glm/")' $P/web_server.py | head -3
