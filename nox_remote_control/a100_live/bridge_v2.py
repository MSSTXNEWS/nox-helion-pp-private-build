#!/usr/bin/env python3
"""NOX A100 GitHub control + RunPod container-log return transport.
Safe operations only. No general shell, signals, deletion or trainer mutation.
"""
import datetime as dt
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.request

NODE="runpod-5f3j8hwyicc0bp"
ROOT=Path("/root/.local/state/nox-a100-live-bridge")
API="https://api.github.com/repos/MSSTXNEWS/nox-helion-pp-private-build/contents/nox_remote_control/a100_live/queue.json?ref=control%2Fnox-a100-live-bridge-20261112"
from train_actions import run_operation,poll_auto_resume
WRITE_OPS={"stage_fast75","prepare_local","resume_training","arm_resume_training","cancel_auto_resume"}
OPS={"gpu","disk","processes","checkpoint","preflight","health","stage_fast75","prepare_local","resume_training","training_status","arm_resume_training","cancel_auto_resume"}
ID=re.compile(r"^[A-Za-z0-9_-]{8,64}$")
POLL_SECONDS=30
LOCAL_CKPT=Path("/root/nox36/ckpt/sft/last")
LOCAL_DATA=Path("/tmp/nox36_local/data/tok")
MODEL=Path("/dev/shm/base36")

def utc(): return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")

def store(path, obj):
    tmp=path.with_suffix(".new")
    with tmp.open("w",encoding="utf-8") as f:
        json.dump(obj,f,ensure_ascii=False,separators=(",",":"))
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp,path)

def report(obj):
    message="NOX_BRIDGE_RECEIPT "+json.dumps(obj,ensure_ascii=True,separators=(",",":"))+"\n"
    data=message.encode("ascii")
    if len(data)>2500:
        raise ValueError("OUTPUT_TOO_LARGE")
    try:
        fd=os.open("/proc/1/fd/1", os.O_WRONLY|os.O_NONBLOCK)
        try: os.write(fd,data)
        finally: os.close(fd)
        return True
    except OSError:
        return False

def gpu():
    try:
        proc=subprocess.run(["nvidia-smi",
              "--query-gpu=name,temperature.gpu,utilization.gpu,memory.used,memory.total",
              "--format=csv,noheader,nounits"],capture_output=True,text=True,timeout=6,
              env={"PATH":"/usr/local/bin:/usr/bin:/bin","LC_ALL":"C"})
        if proc.returncode!=0: return {"state":"HOLD_GPU"}
        parts=[x.strip() for x in proc.stdout.splitlines()[0].split(",")]
        if len(parts)!=5: return {"state":"HOLD_GPU_PARSE"}
        name=parts[0][:70]
        def num(s):
            try: return float(s)
            except ValueError: return None
        return {"state":"MEASURED","name":name,"temp_c":num(parts[1]),
                "usage_pct":num(parts[2]),"vram_mib":num(parts[3]),"vram_total_mib":num(parts[4])}
    except (OSError,subprocess.TimeoutExpired,IndexError): return {"state":"HOLD_GPU"}

def disk():
    try:
        s=os.statvfs("/")
        return {"free_gib":round(s.f_bavail*s.f_frsize/1073741824,2),
                "total_gib":round(s.f_blocks*s.f_frsize/1073741824,2)}
    except OSError: return {"state":"HOLD_DISK"}

def processes():
    names=("train_n36.py","train_n36_fast75.py","learner.py","watchdog_n36_v2.sh")
    results={k:[] for k in names}
    for p in Path("/proc").iterdir():
        if not p.name.isdecimal(): continue
        try:
            args=(p/"cmdline").read_bytes().split(b"\0")
            files={os.path.basename(x.decode(errors="replace")) for x in args[1:] if x}
            for name in names:
                if name in files and len(results[name])<10: results[name].append(int(p.name))
        except (OSError,ValueError): continue
    return results

def checkpoint():
    step=None
    try:
        step_text=(LOCAL_CKPT/"STEP").read_text(encoding="utf-8").strip()
        if step_text.isdecimal(): step=int(step_text)
    except (OSError,UnicodeDecodeError): pass
    return {"step":step,"dir_present":LOCAL_CKPT.is_dir(),
            "step_present":step is not None,"sha_verified":False}

def preflight():
    ck=checkpoint()
    procs=processes()
    dat={"train_pt":(LOCAL_DATA/"train.pt").is_file(),
         "hold_pt":(LOCAL_DATA/"hold.pt").is_file(),
         "model_dir":MODEL.is_dir(),
         "fast75_script":Path("/tmp/NOX_A100_FAST75_V2/START_FAST75.sh").is_file(),
         "checkpoint":ck,
         "trainer_active":bool(procs["train_n36.py"] or procs["train_n36_fast75.py"]),
         "disk":disk()}
    dat["state"]="HOLD_NOT_READY"
    return dat

def inspect(op):
    if op=="gpu":return gpu()
    if op=="disk":return disk()
    if op=="processes":return processes()
    if op=="checkpoint":return checkpoint()
    if op=="preflight":return preflight()
    if op=="health":return {"gpu":gpu(),"disk":disk(),"checkpoint":checkpoint()}
    if op in {"stage_fast75","prepare_local","resume_training","training_status","arm_resume_training","cancel_auto_resume"}:
        return run_operation(op)
    raise ValueError("UNSUPPORTED_OPERATION")

def load_tasks():
    req=urllib.request.Request(API,headers={"User-Agent":"NOX-a100-live-bridge/1",
          "Accept":"application/vnd.github.raw+json","Cache-Control":"no-cache"})
    with urllib.request.urlopen(req,timeout=10) as res: body=res.read(16385)
    if len(body)>16384: raise ValueError("QUEUE_OVERSIZE")
    queue=json.loads(body)
    if not isinstance(queue,dict) or set(queue)!={"schema","node","tasks"}:
        raise ValueError("QUEUE_SCHEMA")
    if queue["schema"]!="nox-live-safe-v1" or queue["node"]!=NODE:
        raise ValueError("QUEUE_TARGET")
    tasks=queue["tasks"]
    if not isinstance(tasks,list) or len(tasks)>10: raise ValueError("QUEUE_LENGTH")
    seen=set()
    for task in tasks:
        if not isinstance(task,dict) or set(task)!={"id","op","expires_utc"}:
            raise ValueError("TASK_SCHEMA")
        ident=task["id"]
        if not isinstance(ident,str) or not ID.fullmatch(ident) or ident in seen:
            raise ValueError("TASK_ID")
        if task["op"] not in OPS: raise ValueError("TASK_OP")
        expires=dt.datetime.fromisoformat(task["expires_utc"].replace("Z","+00:00"))
        if expires.tzinfo is None: raise ValueError("TASK_TIMEZONE")
        seen.add(ident)
    return tasks

def run():
    ROOT.mkdir(parents=True,exist_ok=True)
    with (ROOT/"lock").open("a+") as lock:
        try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            print("NOX_LIVE_BRIDGE_ALREADY_RUNNING",flush=True)
            return
        report({"node":NODE,"event":"STARTED","utc":utc(),"ops":sorted(OPS)})
        while True:
            try:
                tasks=load_tasks()
                for t in tasks:
                    receipt=ROOT/("receipt_"+t["id"]+".json")
                    if receipt.exists(): continue
                    now=dt.datetime.now(dt.timezone.utc)
                    exp=dt.datetime.fromisoformat(t["expires_utc"].replace("Z","+00:00"))
                    result={"node":NODE,"id":t["id"],"op":t["op"],"utc":utc()}
                    if exp<=now or exp-now>dt.timedelta(hours=24):
                        result.update(status="HOLD_EXPIRED")
                    else:
                        data=inspect(t["op"])
                        if t["op"] in WRITE_OPS:
                            state=data.get("state","HOLD_UNKNOWN") if isinstance(data,dict) else "HOLD_BAD_RESPONSE"
                            status="HOLD" if state.startswith("HOLD") else "ACTION_EVALUATED"
                            result.update(status=status,data=data)
                        else:
                            result.update(status="READ_ONLY",data=data)
                    store(receipt,result)
                    report(result)
            except Exception as exc:
                # No exception text or credentials are written to container logs.
                report({"node":NODE,"event":"HOLD_AGENT","error":type(exc).__name__,"utc":utc()})
            try:
                auto=poll_auto_resume()
                if isinstance(auto,dict):
                    report({"node":NODE,"event":"AUTO_RESUME_TICK","utc":utc(),
                            "state":str(auto.get("state","UNKNOWN"))[:100],
                            "resume_step":auto.get("resume_step")})
            except Exception as exc:
                report({"node":NODE,"event":"HOLD_AUTO_RESUME","error":type(exc).__name__,"utc":utc()})
            time.sleep(POLL_SECONDS)

if __name__=="__main__":
    run()
