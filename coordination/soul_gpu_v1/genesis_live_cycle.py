"""NOX GENESIS LIVE CYCLE V1.

A bounded autonomous self-improvement *candidate* loop while the existing
NOX.HELION.exe runs. It NEVER installs generated code, edits release binaries,
performs internet crawling or bypasses S03 native permissions.

No new model downloads or weights training here. This loop provides continuous
read -> plan -> propose -> syntax-check -> evidence -> reevaluate. Native
OneHost/S03/Windows E07 integration is still needed for a real self-updating EXE.
"""
from __future__ import annotations
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone

HERE=Path(__file__).resolve().parent
ROOT=Path(r"C:\NOX_HELION\NOX_NEW") if os.name=="nt" else Path.cwd()
TASKS=(("init",1),("plan",1),("propose",1),("status",1))
MIN_CYCLE_SECONDS=1200
LOW_BATTERY=30
CRITICAL_BATTERY=20
MIN_FREE_BYTES=60*10**9

def utc():return datetime.now(timezone.utc).isoformat()

def record(root:Path,data):
    dest=root/"brain"/"telemetry"/"genesis_live.json"
    dest.parent.mkdir(parents=True,exist_ok=True)
    temp=dest.with_suffix(".json.tmp")
    temp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
    os.replace(temp,dest)

def native_running():
    """Read Windows process table; don't keep evolving after NOX closes."""
    if os.name!="nt":
        return False
    proc=subprocess.run(["tasklist","/FI","IMAGENAME eq NOX.HELION.exe","/FO","CSV","/NH"],
                        capture_output=True,text=True,timeout=12)
    return proc.returncode==0 and "NOX.HELION.exe" in proc.stdout

def battery():
    """Windows system power status; unknown is handled conservatively."""
    if os.name!="nt":return {"ac":None,"percent":None}
    class SYSTEM_POWER_STATUS(ctypes.Structure):
        _fields_=[("ACLineStatus",ctypes.c_byte),("BatteryFlag",ctypes.c_byte),
                 ("BatteryLifePercent",ctypes.c_byte),("SystemStatusFlag",ctypes.c_byte),
                 ("BatteryLifeTime",ctypes.c_uint),("BatteryFullLifeTime",ctypes.c_uint)]
    x=SYSTEM_POWER_STATUS()
    ok=ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(x))
    if not ok: return {"ac":None,"percent":None}
    ac=bool(x.ACLineStatus) if x.ACLineStatus in (0,1) else None
    pct=int(x.BatteryLifePercent) if 0<=x.BatteryLifePercent<=100 else None
    return {"ac":ac,"percent":pct}

def gpu_temperature():
    """Read NVIDIA sensor if available; never assume AMD = NVIDIA."""
    try:
        r=subprocess.run(["nvidia-smi","--query-gpu=temperature.gpu",
                         "--format=csv,noheader,nounits"],capture_output=True,
                         text=True,timeout=6,check=True)
        val=int(r.stdout.splitlines()[0].strip())
        return val if 0<=val<120 else None
    except (OSError,ValueError,IndexError,subprocess.SubprocessError):
        return None

def run_action(root,action):
    cmd=[sys.executable,str(HERE/"genesis_segment1.py"),action,"--root",str(root)]
    return subprocess.run(cmd,capture_output=True,text=True,timeout=360)

def supervise(root:Path,interval:int,cycles:int):
    if interval<MIN_CYCLE_SECONDS:
        raise ValueError("Minimum 20 minutes between self-build candidate cycles")
    root=root.resolve()
    if not (root/"release"/"NOX.HELION.exe").is_file():
        raise RuntimeError("Installed NOX.HELION.exe missing")
    if not (HERE/"genesis_segment1.py").is_file():
        raise RuntimeError("Genesis source missing")
    # Single-instance lock is a persistent file; stale process recovered only
    # after conservative PID check. No force-kill, no deletion of other processes.
    lock=root/"brain"/"telemetry"/"genesis_live.lock"
    lock.parent.mkdir(parents=True,exist_ok=True)
    if lock.exists():
        raise RuntimeError("Existing genesis_live.lock; check previous supervisor before restart")
    with lock.open("x",encoding="utf-8") as f:
        f.write(str(os.getpid()))
    started=0
    try:
        while cycles<=0 or started<cycles:
            if not native_running():
                record(root,{"status":"NOX_CLOSED","timestamp":utc(),
                             "cycles_completed":started,"patches_applied":0})
                return
            power=battery()
            free=shutil.disk_usage(root).free
            temp=gpu_temperature()
            if free<MIN_FREE_BYTES:
                state="DISK_RESERVE_HOLD"
            elif power["ac"] is False and power["percent"] is not None and power["percent"]<=CRITICAL_BATTERY:
                state="BATTERY_CRITICAL_HOLD"
            elif temp is not None and temp>=65:
                state="GPU_COOLING_180S"
            else:
                state="ACTIVE"
            if state=="GPU_COOLING_180S":
                record(root,{"status":state,"timestamp":utc(),"gpu_c":temp,
                             "pause_seconds":180,"battery":power,"cycles_completed":started})
                time.sleep(180)
                # Continue monitoring, do not run a cycle above 65 C.
                continue
            if state!="ACTIVE":
                record(root,{"status":state,"timestamp":utc(),"gpu_c":temp,
                             "battery":power,"disk_free":free,"cycles_completed":started})
                time.sleep(60)
                continue
            # Save G0 + 8-Core worm plan on first iteration. These are real
            # local bookkeeping actions, NOT active web research worms.
            actions=("init","plan","propose","status") if started==0 else ("propose","status")
            results=[]
            for action in actions:
                if not native_running():break
                try:
                    r=run_action(root,action)
                    results.append({"action":action,"exit_code":r.returncode,
                                    "result_tail":r.stdout[-3000:] if r.returncode==0 else r.stderr[-1200:]})
                    if r.returncode!=0:break
                except (OSError,subprocess.SubprocessError) as exc:
                    results.append({"action":action,"error":str(exc)[:250]})
                    break
            started+=1
            record(root,{"status":"CYCLE_FINISHED_REVIEW_ONLY","timestamp":utc(),
                         "cycle":started,"gpu_c":temp,"battery":power,
                         "actions":results,"model_weights_trained":False,
                         "worms_network_fetched":False,"patches_applied":0,
                         "exe_rebuilt":False,"native_s03_integrated":False,
                         "next_cycle_earliest_seconds":interval})
            # Stop immediately when EXE exits, even during scheduled delay.
            end=time.monotonic()+interval
            while time.monotonic()<end:
                if not native_running():return
                time.sleep(min(15,max(0.5,end-time.monotonic())))
    finally:
        # Only remove own lock if still owned by our PID.
        try:
            if lock.read_text(encoding="utf-8").strip()==str(os.getpid()):
                lock.unlink()
        except OSError:
            pass

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,default=ROOT)
    p.add_argument("--interval",type=int,default=1800)
    p.add_argument("--cycles",type=int,default=0,help="0: as long as NOX runs")
    a=p.parse_args()
    supervise(a.root,a.interval,a.cycles)
