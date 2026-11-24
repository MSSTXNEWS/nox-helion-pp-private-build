RAW=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300
curl -fsSL "$RAW/qa_audit.py?x" -o /workspace/nox/qa_audit.py; curl -fsSL "$RAW/qa_ctl.py?x" -o /workspace/nox/qa_ctl.py
F=/workspace/nox/web/pkg/server/web_server.py
grep -q _glm_compat $F || { cp $F $F.bak_c300_glm; python3 - "$F" <<'P'
import sys;f=sys.argv[1];s=open(f).read()
m='''    def _glm_compat(self, p):
        import urllib.request, json as _j
        try:
            if p.endswith("/models"): data=urllib.request.urlopen("http://127.0.0.1:8200/v1/models",timeout=5).read()
            else: data=_j.dumps({"source":"core/health","health":_j.loads(urllib.request.urlopen("http://127.0.0.1:8090/health",timeout=5).read())}).encode()
            code=200
        except Exception as e: data=_j.dumps({"error":str(e)}).encode(); code=503
        self.send_response(code); self.send_header("Content-Type","application/json"); self.send_header("Content-Length",str(len(data))); self.end_headers(); self.wfile.write(data)

'''
i=s.index("    def _proxy("); s=s[:i]+m+s[i:]
a='        if p.startswith("/glm/"): return self._proxy("GET", p[4:], None)'
s=s.replace(a,'        if p in ("/glm/v1/models","/glm/v1/nox/stats"): return self._glm_compat(p)\n'+a,1)
open(f,'w').write(s)
P
python3 -m py_compile $F && /workspace/nox/web/pkg/server/run_web.sh restart >/dev/null 2>&1; sleep 3; }
for u in glm/v1/models glm/v1/nox/stats; do echo "$u $(curl -s -o /dev/null -w '%{http_code}' -m8 http://127.0.0.1:8091/$u)"; done
echo '{}' > /dev/null; rm -f /workspace/nox/web/site/qa/audit.json
pkill -f qa_loop.sh; nohup setsid /workspace/nox/qa_loop.sh >/dev/null 2>&1 < /dev/null &
echo restarted
