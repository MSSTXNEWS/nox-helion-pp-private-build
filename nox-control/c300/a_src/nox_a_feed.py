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
PORTS={"тело":8104,"подъядро":8105,"судья_учитель":8106,"второй_судья":8141,"судьи":8300,"каскад":8400,"операторы":8130,"API-шлюз":8120,"рисунок":8097}
def port_ok(port):
    for path in ("/health","/v1/models"):
        try:
            urllib.request.urlopen("http://127.0.0.1:%d%s"%(port,path),timeout=3); return True,path
        except urllib.error.HTTPError as e: return True,"%s HTTP %d"%(path,e.code)
        except Exception: pass
    return False,""
def gpu():
    try:
        r=subprocess.run(["nvidia-smi","--query-gpu=memory.used,memory.total,utilization.gpu","--format=csv,noheader,nounits"],capture_output=True,text=True,timeout=5).stdout.strip().splitlines()[0]
        u,t,g=[float(x) for x in r.split(",")]
        return {"vram_used_mib":u,"vram_total_mib":t,"vram_pct":round(100*u/t,1),"gpu_util_pct":g}
    except Exception: return None
def tail(path,n):
    try: return [l.rstrip()[:220] for l in open(path,errors="ignore").read().splitlines()[-n:]]
    except Exception: return []
def live():
    ports={k:dict(zip(("ok","via"),port_ok(v))) for k,v in PORTS.items()}
    rnd=[l for l in tail("/workspace/nox/agent/out/autotrain.log",400) if "раунд" in l]
    ck=sorted(os.listdir("/workspace/nox/distill_v2/ckpt_keep")) if os.path.isdir("/workspace/nox/distill_v2/ckpt_keep") else []
    json.dump({"ts":time.time(),"ports":ports,"gpu":gpu(),"round":rnd[-1] if rnd else None,"autotrain_tail":tail("/workspace/nox/agent/out/autotrain.log",6),"ckpt_keep":ck[-12:],"ops_tail":tail("/workspace/nox/agent/out/ops_changes.log",6)},open(D+"/live.json","w"),ensure_ascii=False)
n=0
while True:
    s=stats()
    if s:
        with open(H,"a") as f: f.write(json.dumps(s,ensure_ascii=False)+"\n")
    if n%2==0:
        try: live()
        except Exception: pass
    if n%4==0:
        try: logs()
        except Exception: pass
    if n%240==0 and os.path.exists(H):
        L=open(H).read().splitlines()[-4000:]; open(H,"w").write("\n".join(L)+"\n")
    n+=1; time.sleep(15)
