import subprocess, time, json, urllib.request, re, shutil, os
LOG="/root/nox/logs/flash_ab3.log"
BIN="/root/nox/llama.cpp-f/build/bin/llama-server"; M="/dev/shm/glm53f/GLM-5.3-Flash-UD-Q4_K_XL-00001-of-00006.gguf"
BASE="--host 127.0.0.1 --port 8081 --parallel 4 -c 32768 -fa on --jinja -ot exps=CPU --reasoning off --no-op-offload -ub 512 -b 2048"
def log(s):
    open(LOG,"a").write(time.strftime("%H:%M:%S ")+s+"\n")
def sh(c): return subprocess.run(c,shell=True,capture_output=True,text=True)
def start(cpus,t,ngl,extra=""):
    sh("pkill -9 -f 'llama-server.*--port 8081'"); time.sleep(4)
    cmd="GGML_CUDA_NO_PINNED=1 nohup nice -n 19 taskset -c %s %s -m %s %s -ngl %d -t %d -tb %d %s > /root/nox/logs/glm_8081.log 2>&1 &"%(cpus,BIN,M,BASE,ngl,t,t,extra)
    sh(cmd)
    for i in range(80):
        time.sleep(3)
        if sh("curl -sf -m2 127.0.0.1:8081/health").returncode==0: return cmd
        if sh("pgrep -f 'llama-server.*--port 8081'").returncode!=0: return None
    return None
def bench():
    msg="Объясни подробно, своими словами, как работает память человека: кратковременная, долговременная, как формируются воспоминания и почему мы забываем."
    b={"messages":[{"role":"user","content":msg}],"max_tokens":120,"temperature":0,"cache_prompt":False}
    r=json.load(urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8081/v1/chat/completions",json.dumps(b).encode(),{"Content-Type":"application/json"}),timeout=900))
    t=r.get("timings",{}); return t.get("predicted_per_second",0), t.get("prompt_per_second",0)
sh("pkill -f glm_watch.sh")
cfgs=[("A t18 c0-17 ngl24","0-17",18,24,""),("B t24 c0-23 ngl24","0-23",24,24,""),("C t27 c0-26 ngl24","0-26",27,24,""),
      ("D t24 ngl32","0-23",24,32,""),("E t24 ngram","0-23",24,24,"--spec-type ngram-simple --spec-draft-n-max 8")]
res=[]
for name,cpus,t,ngl,extra in cfgs:
    cmd=start(cpus,t,ngl,extra)
    if not cmd: log(name+" FAILED start "+sh("grep -iE 'error|out of memory' /root/nox/logs/glm_8081.log | head -2").stdout.strip()[:200]); continue
    try:
        bench(); tg,pp=bench()
    except Exception as e: log(name+" bench err %s"%e); continue
    log("%s tg %.2f pp %.1f"%(name,tg,pp)); res.append((tg,name,cmd))
res.sort(reverse=True)
best=res[0]; log("BEST "+best[1])
open("/root/nox/start_glm.sh","w").write("#!/bin/bash\n# автоподбор flash_ab3 %s\npkill -9 -f 'llama-server.*--port 8081'; sleep 3\n%s\n"%(time.strftime("%F %T"),best[2]))
sh("bash /root/nox/start_glm.sh"); time.sleep(40)
sh("(nohup setsid bash /root/nox/glm_watch.sh >/dev/null 2>&1 </dev/null &)")
log("DONE health=%s"%sh("curl -s -m3 -o /dev/null -w %{http_code} 127.0.0.1:8081/health").stdout)
