"""NOX GPU WORM V1. A bounded, fail-closed supervisor for SAFE70 target 11120.
Not self-replicating; it simply restarts the authorized local trainer if safe.
Never hides a training error or invents a saved step.
"""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from contextlib import suppress

HERE=Path(__file__).resolve().parent
ROOT=Path(r"C:\NOX_HELION\NOX_NEW")
TARGET=11120
MAX_SESSIONS=6
MAX_THERMAL_EXHAUSTIONS=3
RECHECK_SECONDS=20
THERMAL_REST_SECONDS=900

sys.path.insert(0,str(HERE))
from nox_gpu_target_11120 import temperature,battery,inputs,latest_checkpoint,ROOT as TRAIN_ROOT

def note(event,**kw):
    data={"timestamp_utc":datetime.now(timezone.utc).isoformat(),"event":event,**kw}
    print("NOX WORM "+json.dumps(data,ensure_ascii=False),flush=True)
    root=ROOT/"brain"/"telemetry"
    root.mkdir(parents=True,exist_ok=True)
    p=root/"worm_status.json"
    tmp=p.with_name("." + p.name + "." + str(os.getpid()) + ".tmp")
    tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
    try:
        for _ in range(12):
            try:
                os.replace(tmp,p)
                return
            except PermissionError:
                time.sleep(.2)
        # This log is informational; protecting the trainer does not depend on
        # a successful update to a UI JSON status file.
        os.replace(tmp,p.with_name("worm_status_safe70.json"))
        print("NOX WORM TELEMETRY: status file locked; sidecar saved",flush=True)
    finally:
        with suppress(OSError):
            tmp.unlink(missing_ok=True)

def assert_idle():
    if os.name!="nt":raise RuntimeError("Windows only")
    script=(
        "$self="+str(os.getpid())+";"
        "$a=Get-CimInstance Win32_Process | Where-Object {"
        "$_.Name -match '^python(?:w)?[.]exe$' -and "
        "$_.CommandLine -match 'train_directml_lora[.]py|nox_gpu_(?:safe65_v2|10000|target_11120)[.]py' "
        "}; $a | Select-Object -ExpandProperty ProcessId"
    )
    r=subprocess.run(["powershell.exe","-NoProfile","-NonInteractive","-Command",script],
                     text=True,capture_output=True,timeout=20)
    if r.returncode!=0:raise RuntimeError("Unable to inspect GPU processes: "+r.stderr[-400:])
    existing=[int(x) for x in r.stdout.splitlines() if x.strip().isdigit()]
    if existing:raise RuntimeError("Another GPU worker/controller already exists: "+str(existing))

def check_checkpoint():
    step,cp,_,_=inputs() # same source as controller. No model downloads.
    if step>TARGET:raise RuntimeError("Unexpected checkpoint beyond target; no training")
    if step>=TARGET:return step,cp
    weight=cp/"adapter_model.safetensors"
    if not weight.is_file() or weight.stat().st_size<1000:raise RuntimeError("Missing saved weights")
    from safetensors import safe_open
    with safe_open(str(weight),framework="pt",device="cpu") as f:
        keys=list(f.keys())
        if not keys:raise RuntimeError("Empty saved checkpoint")
        # Validate tensor metadata and actual payload, not just filename.
        for name in keys:
            if f.get_tensor(name).numel()<1:raise RuntimeError("Empty tensor: "+name)
    return step,cp

def safe_to_start():
    import shutil
    if shutil.disk_usage(ROOT).free<60_000_000_000:
        raise RuntimeError("Less than 60GB free disk reserve")
    hot=temperature() # fails closed on sensor unavailability
    ac,pct=battery()
    if hot>=65: return False,"HOTSPOT_WAIT",hot,pct
    if not ac and pct<=30:return False,"BATTERY_WAIT",hot,pct
    return True,"SAFE",hot,pct

def supervised():
    assert_idle()
    controller=HERE/"nox_gpu_target_11120.py"
    if not controller.is_file():raise RuntimeError("Target controller missing")
    step,_=check_checkpoint()
    note("START",saved_step=step,goal=TARGET,policy="SAFE70")
    if step>=TARGET:
        note("GOAL",saved_step=step)
        return 0
    sessions=0
    exhaustions=0
    last_step=step
    while sessions<MAX_SESSIONS:
        # Wait on safe conditions, capped to avoid hanging forever on broken sensor.
        checks=0
        while True:
            ok,why,hot,pct=safe_to_start()
            if ok:break
            note("WAIT",reason=why,hotspot_c=hot,battery_pct=pct,saved_step=last_step)
            checks+=1
            if checks>=180:raise RuntimeError("Thermal/power wait timeout")
            time.sleep(RECHECK_SECONDS)
        step,cp=check_checkpoint()
        if step>=TARGET:
            note("GOAL",saved_step=step)
            return 0
        sessions+=1
        note("TRAINER_STARTED",session=sessions,saved_step=step,checkpoint=str(cp),hotspot_c=hot)
        # The target controller owns the thermal process kill and checkpoint.
        # Run foreground, keep supervisor attached to avoid hidden orphaned work.
        proc=subprocess.Popen([sys.executable,"-u",str(controller)],
             cwd=str(HERE),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
             bufsize=1,universal_newlines=True)
        tail=[]
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                print(line,end="",flush=True)
                tail.append(line.rstrip())
                if len(tail)>50:tail.pop(0)
            rc=proc.wait()
        except KeyboardInterrupt:
            # Interrupt the full worker tree; do NOT restart.
            subprocess.run(["taskkill.exe","/PID",str(proc.pid),"/T","/F"],
                capture_output=True,timeout=20)
            note("MANUAL_STOP",session=sessions)
            raise
        step,cp=check_checkpoint()
        note("TRAINER_EXIT",session=sessions,returncode=rc,saved_step=step)
        if step>=TARGET:
            note("GOAL",saved_step=step)
            return 0
        output="\n".join(tail)
        if rc==0:
            # The program must not report success before reaching target.
            raise RuntimeError("Controller exited 0 before target; no restart")
        if "EXCESSIVE_THERMAL_STOPS" not in output:
            raise RuntimeError("Nonthermal trainer failure. No restart. Last lines:\n"+output[-1600:])
        if step<=last_step:raise RuntimeError("Repeated thermal stop without saved progress; no restart")
        exhaustions+=1
        if exhaustions>=MAX_THERMAL_EXHAUSTIONS:
            raise RuntimeError("Safety limit: 3 exhausted thermal sessions; saved checkpoint intact")
        note("THERMAL_REST",saved_step=step,rest_seconds=THERMAL_REST_SECONDS)
        time.sleep(THERMAL_REST_SECONDS)
        last_step=step
    raise RuntimeError("Session safety cap before target")

if __name__=="__main__":
    try:
        raise SystemExit(supervised())
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as ex:
        note("HALT",error=str(ex)[:900])
        print("NOX WORM HALT:",ex,file=sys.stderr,flush=True)
        raise SystemExit(1)
