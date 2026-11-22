import re, shutil, subprocess, time
N="/root/nox/"; theirs=open(N+"web_server.py").read(); mine=open(N+"web_server.py.bak-173").read()
shutil.copy(N+"web_server.py", N+"web_server.py.theirs_"+time.strftime("%H%M%S"))
a=theirs.index("# ---- /api/pc-metrics"); b=theirs.index("\nclass ", a)
block=theirs[a:b].rstrip()+"\n"
# не тащить лишние глобалы, которые уже есть у меня
i=mine.index("\nclass "); mine=mine[:i]+"\n"+block+mine[i:]
routes=[l for l in theirs.split("\n") if 'p == "/api/pc-metrics"' in l or 'p == "/api/health"' in l]
anc=re.search(r'\n(\s+)if p\.startswith\("/memory/"\): return self\._memory\("GET"', mine)
ind=anc.group(1); mine=mine[:anc.start()]+"\n"+"\n".join(ind+l.strip() for l in routes)+mine[anc.start():]
for imp in ("glob","subprocess","time"):
    if not re.search(r"^import .*\b%s\b"%imp, mine, re.M): mine=mine.replace("import os, sys,","import os, sys, %s,"%imp,1)
open(N+"web_server.py.merged","w").write(mine)
r=subprocess.run(["python3","-m","py_compile",N+"web_server.py.merged"],capture_output=True,text=True); print("compile",r.returncode,r.stderr[-300:])
if r.returncode==0: shutil.move(N+"web_server.py.merged",N+"web_server.py"); print("installed routes",len(routes),"dmem",mine.count("_dmem()"),"pcm",mine.count("pc_metrics"))
