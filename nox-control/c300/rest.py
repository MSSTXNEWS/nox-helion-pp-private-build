import re, shutil, subprocess, time, json, urllib.request
N="/root/nox/"; src=N+"web_server.py.bak-170"; cur=N+"web_server.py"; ts=time.strftime("%H%M%S")
shutil.copy(cur, cur+".small_"+ts)
s=open(src).read()
print("ok_break", s.count("if ok: break"))
old='c.request("GET", "/health"); d["glm_busy"] = c.getresponse().status == 503'
s=s.replace(old,'c.request("GET", "/slots"); d["glm_busy"] = any(x.get("is_processing") for x in json.loads(c.getresponse().read() or b"[]"))')
print("busy", s.count('"/slots"'))
s=re.sub(r'GLM-5\.3(?!-Flash)','GLM-5.3-Flash',s)
open(cur,"w").write(s)
r=subprocess.run(["python3","-m","py_compile",cur],capture_output=True,text=True); print("compile",r.returncode,r.stderr[-200:])
