import shutil, time, subprocess, re
p="/root/nox/web_server.py"; s=open(p).read(); shutil.copy(p,p+".bak_w1_"+time.strftime("%H%M%S"))
pat='            try: _soul = open("/root/nox/repo/nox-control/qs6/soul_prompt_ru.txt", encoding="utf-8").read()\n'
print("soul read", s.count(pat))
if "Ритуальные фразы" not in s:
    s=s.replace(pat, pat+'            except Exception: _soul = "Ты NOX HELION."\n            _soul = "\\n".join(l for l in _soul.split("\\n") if "Ритуальные фразы" not in l)\n            if False:\n                pass\n',1)
open(p,"w").write(s); r=subprocess.run(["python3","-m","py_compile",p],capture_output=True,text=True); print("compile",r.returncode,r.stderr[-200:])
if r.returncode: shutil.copy(sorted(__import__("glob").glob(p+".bak_w1_*"))[-1],p); print("REVERTED")
