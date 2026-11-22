import shutil, time, subprocess
p="/root/nox/web_server.py"; s=open(p).read(); shutil.copy(p,p+".bak_sl_"+time.strftime("%H%M%S"))
a='"max_tokens": 500, "cache_prompt": True,'
print("slot", s.count(a)); s=s.replace(a,'"max_tokens": 500, "cache_prompt": True, "id_slot": 0,')
b='"\\n- ".join(_facts)[:1800]'; print("facts", s.count(b)); s=s.replace(b,'"\\n- ".join(_facts[:4])[:700]')
open(p,"w").write(s); r=subprocess.run(["python3","-m","py_compile",p],capture_output=True,text=True); print("compile",r.returncode,r.stderr[-200:])
