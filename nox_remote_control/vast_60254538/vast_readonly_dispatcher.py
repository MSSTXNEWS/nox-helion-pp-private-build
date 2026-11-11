#!/usr/bin/env python3
"""NOX Vast.ai read-only dispatcher. Never runs user-supplied shell commands."""
import datetime as dt, fcntl, json, os, pathlib, re, subprocess, sys, time, urllib.request
NODE="vast-60254538"
ROOT=pathlib.Path("/root/nox/remote_control/vast_60254538")
URL="https://api.github.com/repos/MSSTXNEWS/nox-helion-pp-private-build/contents/nox_remote_control/vast_60254538/queue.json?ref=control%2Fvast-60254538"
OPS={"gpu","processes","disk","checkpoints","health"}
def stamp(): return dt.datetime.now(dt.timezone.utc).isoformat()
def save(name, data):
    ROOT.mkdir(parents=True,exist_ok=True)
    dest=ROOT/name; temp=ROOT/(name+"."+str(os.getpid())+".tmp")
    with temp.open("w",encoding="utf-8") as f:
        json.dump(data,f,ensure_ascii=False,indent=2); f.flush(); os.fsync(f.fileno())
    os.replace(temp,dest)
def cmd(argv):
    try:
        p=subprocess.run(argv,timeout=10,capture_output=True,text=True,env={"PATH":"/usr/local/bin:/usr/bin:/bin","LC_ALL":"C"})
        return {"exit":p.returncode,"stdout":p.stdout[:3000] if p.returncode==0 else "","error":"COMMAND_FAILED" if p.returncode else ""}
    except (OSError,subprocess.TimeoutExpired) as e: return {"error":type(e).__name__}
def gpu():
    return cmd(["nvidia-smi","--query-gpu=name,temperature.gpu,utilization.gpu,memory.used,memory.total,power.draw","--format=csv,noheader"])
def disk():
    data={}
    for p in ("/workspace","/root/nox"):
        try:
            s=os.statvfs(p)
            data[p]={"free_gib":round(s.f_bavail*s.f_frsize/(1024**3),2),"total_gib":round(s.f_blocks*s.f_frsize/(1024**3),2)}
        except OSError: data[p]={"status":"HOLD_NO_MOUNT"}
    return data
def processes():
    rows=[]
    for p in pathlib.Path("/proc").iterdir():
        if not p.name.isdecimal(): continue
        try:
            args=(p/"cmdline").read_bytes().split(b"\0")
            matches=[pathlib.PurePosixPath(a.decode("utf8","replace")).name for a in args if re.search(rb"(nox|learner\.py|chat_proxy\.py|backup_drive\.py)",a,re.I)]
            if matches: rows.append({"pid":int(p.name),"entry":matches[0][:80]})
        except (OSError,ValueError): pass
    return {"count":len(rows),"items":sorted(rows,key=lambda x:x["pid"])[:40]}
def checkpoints():
    files=[]
    for folder in ("/root/nox/checkpoints","/workspace/nox/checkpoints"):
        r=pathlib.Path(folder)
        if r.is_dir():
            for p in r.rglob("*"):
                if p.is_file() and p.suffix in (".pt",".ckpt",".safetensors"):
                    try: files.append({"name":p.name[:90],"bytes":p.stat().st_size})
                    except OSError: pass
                if len(files)>=25: break
    return {"items":files,"note":"metadata only; hash not verified"}
def inspect(op):
    if op=="gpu": return gpu()
    if op=="disk": return disk()
    if op=="processes": return processes()
    if op=="checkpoints": return checkpoints()
    if op=="health": return {"gpu":gpu(),"disk":disk(),"processes":processes()}
    raise ValueError("UNAUTHORIZED_OPERATION")
def tasks():
    request=urllib.request.Request(URL,headers={"User-Agent":"NOX-safe-observer/2","Accept":"application/vnd.github.raw+json","Cache-Control":"no-cache"})
    with urllib.request.urlopen(request,timeout=12) as response: data=response.read(16385)
    if len(data)>16384: raise ValueError("OVERSIZED_QUEUE")
    q=json.loads(data)
    if not isinstance(q,dict) or set(q)!={"schema","node","tasks"} or q["schema"]!="nox-vast-readonly-v1" or q["node"]!=NODE: raise ValueError("INVALID_QUEUE")
    arr=q["tasks"]
    if not isinstance(arr,list) or len(arr)>10: raise ValueError("TASK_LIMIT")
    seen=set()
    for x in arr:
        if not isinstance(x,dict) or set(x)!={"id","op","expires_utc"}: raise ValueError("UNEXPECTED_TASK_FIELDS")
        if not isinstance(x["id"],str) or not re.fullmatch("[A-Za-z0-9_-]{8,64}",x["id"]) or x["id"] in seen: raise ValueError("INVALID_ID")
        if x["op"] not in OPS or not isinstance(x["expires_utc"],str): raise ValueError("UNAUTHORIZED_OPERATION")
        exp=dt.datetime.fromisoformat(x["expires_utc"].replace("Z","+00:00"))
        if exp.tzinfo is None: raise ValueError("INVALID_EXPIRY")
        seen.add(x["id"])
    return arr
def tick():
    now=dt.datetime.now(dt.timezone.utc)
    for t in tasks():
        f="receipt_"+t["id"]+".json"
        if (ROOT/f).exists(): continue
        exp=dt.datetime.fromisoformat(t["expires_utc"].replace("Z","+00:00"))
        result={"id":t["id"],"node":NODE,"operation":t["op"],"utc":stamp()}
        if now>exp or exp-now>dt.timedelta(hours=24): result["status"]="HOLD_EXPIRED"
        else:
            result["status"]="READ_ONLY"
            result["data"]=inspect(t["op"])
        save(f,result)
        print(json.dumps({"id":t["id"],"status":result["status"]}),flush=True)
def main():
    ROOT.mkdir(parents=True,exist_ok=True)
    with (ROOT/"agent.lock").open("a+") as lock:
        try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: print("ALREADY_RUNNING"); return
        while True:
            try: tick()
            except Exception as e: save("last_error.json",{"utc":stamp(),"status":"HOLD","exception":type(e).__name__})
            if "--once" in sys.argv: break
            time.sleep(180)
if __name__=="__main__": main()
