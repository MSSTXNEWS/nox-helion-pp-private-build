S=/workspace/nox/web/site; P=/workspace/nox/web/pkg/server
/workspace/nox/venv/bin/python - <<'PYEOF'
w='/workspace/nox/web/pkg/server/web_server.py'; L=open(w,encoding='utf-8').read().split('\n')
i=[k for k,l in enumerate(L) if l.startswith('        if p == "/glm/props"')][0]; line=L.pop(i)
j=[k for k,l in enumerate(L) if l.startswith('        if p.startswith("/glm/"): return self._proxy("GET"')][0]
L.insert(j,line); open(w,'w',encoding='utf-8').write('\n'.join(L)); print('moved',i,j)
PYEOF
/workspace/nox/venv/bin/python -m py_compile $P/web_server.py && echo COMPILE_OK && bash $P/run_web.sh restart 2>&1 | tail -1
sleep 3; for u in /glm/props /api/nox/status /memory/health; do echo $u $(curl -s -m8 -w " %{http_code}" http://127.0.0.1:8091$u | tail -c 120); done
for n in index cinema music photo studio tools; do touch $S/qa/rework/$n.fixed; done
cd /workspace/nox; setsid nohup flock -n /tmp/qa.lock /workspace/nox/venv/bin/python /workspace/nox/qa_ctl.py > /tmp/fx_qa2.out 2>&1 < /dev/null & 
sleep 1; echo qa-started
