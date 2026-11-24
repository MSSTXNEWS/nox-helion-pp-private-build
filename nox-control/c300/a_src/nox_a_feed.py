#!/usr/bin/env python3
"""NOX · запись реальных данных для страниц-датчиков: история органов (каждые 15 с) и разбор логов обучения (раз в 60 с)."""
import json,os,re,time,glob,subprocess,urllib.request
D="/workspace/nox/web/site/data"; os.makedirs(D,exist_ok=True)
H=D+"/organs_hist.jsonl"; T=D+"/train_logs.json"
RX=re.compile(r"шаг (\d+), loss ([\d.]+)(?:, holdout CE ([\d.]+))?")
def stats():
    try:
        h=json.loads(urllib.request.urlopen("http://127.0.0.1:8091/glm/v1/nox/stats",timeout=6).read())["health"]
        return {"ts":round(time.time(),1),"organs":h.get("organs",{}),"turns":h.get("turns"),"glm":(h.get("glm") or {}).get("state"),"fast":h.get("fast")}
    except Exception: return None
def logs():
    runs={}
    for f in sorted(glob.glob("/workspace/nox/agent/out/train*.log")+glob.glob("/workspace/nox/agent/out/pilot_train.log")+glob.glob("/workspace/nox/agent/out/autotrain.log")):
        pts=[]
        for l in open(f,errors="ignore"):
            m=RX.search(l)
            if m: pts.append({"step":int(m.group(1)),"loss":float(m.group(2)),"ce":float(m.group(3)) if m.group(3) else None})
        if pts: runs[os.path.basename(f)]={"points":pts[-2000:],"mtime":os.path.getmtime(f)}
    r=subprocess.run("pgrep -af 'train_student|autotrain|unsloth|trl|axolotl' | grep -v pgrep | grep -v nox_a_feed | head -1",shell=True,capture_output=True,text=True).stdout.strip()
    json.dump({"ts":time.time(),"running":bool(r),"runs":runs},open(T,"w"),ensure_ascii=False)
n=0
while True:
    s=stats()
    if s:
        with open(H,"a") as f: f.write(json.dumps(s,ensure_ascii=False)+"\n")
    if n%4==0:
        try: logs()
        except Exception: pass
    if n%240==0 and os.path.exists(H):
        L=open(H).read().splitlines()[-4000:]; open(H,"w").write("\n".join(L)+"\n")
    n+=1; time.sleep(15)
