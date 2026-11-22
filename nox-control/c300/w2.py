import shutil, time, subprocess
p="/root/nox/web_server.py"; s=open(p).read(); shutil.copy(p,p+".bak_w2_"+time.strftime("%H%M%S"))
a='            except Exception: _soul = "Ты NOX HELION."\n'
print("anchor", s.count(a))
if "Ритуальные фразы" not in s and s.count(a)==1:
    s=s.replace(a, a+'            _soul = "\\n".join(l for l in _soul.split("\\n") if "Ритуальные фразы" not in l)\n')
open(p,"w").write(s); r=subprocess.run(["python3","-m","py_compile",p],capture_output=True,text=True); print("compile",r.returncode,r.stderr[-200:])
if r.returncode: shutil.copy(sorted(__import__("glob").glob(p+".bak_w2_*"))[-1],p); print("REVERTED")
