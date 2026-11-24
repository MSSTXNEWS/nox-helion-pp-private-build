import shutil, time, subprocess, os
p="/workspace/nox/web/pkg/server/web_server.py"; s=open(p).read(); ts=time.strftime("%H%M%S"); shutil.copy(p,p+".bak_c300_"+ts)
DRV='os.environ.get("NOX_DRIVE", "127.0.0.1:18765")'
g='        if p.startswith("/tts/"): return self._proxy("GET", p[4:] + qs, None, TTS, "TTS (127.0.0.1:8094)")\n'
po='        if p.startswith("/tts/"): return self._proxy("POST", p[4:] + qs, raw, TTS, "TTS (127.0.0.1:8094)", self.headers.get("Content-Type"))\n'
if "/drive/" not in s:
    assert s.count(g)==1 and s.count(po)==1
    s=s.replace(g, g+'        if p == "/drive" or p.startswith("/drive/"): return self._proxy("GET", (p[6:] or "/") + qs, None, %s, "Google Диск (мост)")\n' % DRV)
    s=s.replace(po, po+'        if p.startswith("/drive/"): return self._proxy("POST", p[6:] + qs, raw, %s, "Google Диск (мост)", self.headers.get("Content-Type"))\n' % DRV)
open(p,"w").write(s)
r=subprocess.run(["python3","-m","py_compile",p],capture_output=True,text=True); print("compile",r.returncode,r.stderr[-200:])
if r.returncode: shutil.copy(p+".bak_c300_"+ts,p); print("REVERTED")
d="/workspace/nox/web/site/vendor/glasskit"; os.makedirs(d,exist_ok=True)
open(d+"/glasskit.min.css","w").write(":root{--gk-bg:rgba(14,18,28,.55);--gk-border:rgba(160,200,255,.18);--gk-blur:14px}"
 ".glass,.gk-glass{background:var(--gk-bg);border:1px solid var(--gk-border);backdrop-filter:blur(var(--gk-blur)) saturate(140%);-webkit-backdrop-filter:blur(var(--gk-blur)) saturate(140%);border-radius:14px;box-shadow:0 8px 32px rgba(0,0,0,.35),inset 0 1px 0 rgba(255,255,255,.06)}"
 ".gk-card{padding:12px 14px}.gk-btn{background:rgba(120,170,255,.12);border:1px solid var(--gk-border);border-radius:10px;color:inherit;padding:6px 12px;cursor:pointer}.gk-btn:hover{background:rgba(120,170,255,.22)}\n")
print("glasskit ok")
