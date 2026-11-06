"""NOX FORGE / read-only local training & Radeon telemetry V1.

Sources: existing NOX-owned brain/telemetry/training.json and actual
brain/intelligence/adapters/NOX_GPU_* training outputs, plus local
LibreHardwareMonitor Remote Web Server. No synthetic training, no STOP authority,
no changing a GPU process, no model downloads.
"""
from __future__ import annotations
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
from urllib.request import urlopen

def _json(path):
    try:
        if path.stat().st_size>2_000_000: return None
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, UnicodeError): return None

def _temp_number(raw):
    if not isinstance(raw,str) or "°" not in raw: return None
    m=re.search(r"(?<!\d)(\d{1,3}(?:[.,]\d+)?)\s*°\s*C",raw,re.I)
    if not m:return None
    n=float(m.group(1).replace(",","."))
    return n if 0<n<115 else None

def amd_sensor():
    """Match only the discrete RX6650M, never CPU, integrated GPU or voltage."""
    try:
        with urlopen("http://127.0.0.1:8085/data.json",timeout=4) as res:
            obj=json.loads(res.read(3_000_000))
    except (OSError,ValueError,UnicodeError):
        return {"gpu_hotspot_c":None,"gpu_core_c":None,"source":"UNAVAILABLE"}
    results={"gpu_hotspot_c":None,"gpu_core_c":None,"source":"LHM_8085"}
    def walk(node,within=False,depth=0):
        if depth>35 or not isinstance(node,dict):return
        name=str(node.get("Text","")).strip()
        # A nested hardware node begins its own scope. Never inherit another GPU.
        if re.search(r"(?:AMD\s+)?Radeon.*RX\s*6650M",name,re.I):within=True
        elif re.search(r"(?:Ryzen|Radeon|NVIDIA|GeForce).*GPU",name,re.I) and "6650M" not in name:
            within=False
        if within and name=="GPU Hot Spot":
            results["gpu_hotspot_c"]=_temp_number(str(node.get("Value","")))
        if within and name=="GPU Core":
            value=_temp_number(str(node.get("Value","")))
            if value is not None:results["gpu_core_c"]=value
        children=node.get("Children") or []
        if isinstance(children,list):
            for child in children:walk(child,within,depth+1)
    walk(obj)
    if results["gpu_hotspot_c"] is None and results["gpu_core_c"] is None:
        results["source"]="NO_DISCRETE_GPU_TEMPERATURE"
    return results

def _process_active(pid):
    if os.name!="nt" or not isinstance(pid,int) or pid<=0:return False
    script=(
        "$x=Get-CimInstance Win32_Process -Filter 'ProcessId="+str(pid)+"';"
        "if($x -and $x.Name -match '^python' -and "
        "$x.CommandLine -match 'train_directml_lora[.]py'){Write-Output 'YES'}"
    )
    try:
        p=subprocess.run(["powershell.exe","-NoProfile","-NonInteractive","-Command",script],
                         capture_output=True,text=True,timeout=6)
        return p.returncode==0 and p.stdout.strip()=="YES"
    except (OSError,subprocess.SubprocessError):return False

def _recent_run(root):
    # Existing run directories only. Do not scan user's private folders.
    candidates=[]
    base=root/"brain"/"intelligence"/"adapters"
    if base.is_dir() and not base.is_symlink():
        for p in base.iterdir():
            if not p.is_dir() or p.is_symlink() or not p.name.startswith(("NOX_GPU_","SAFE65_","GPU_")):continue
            file=p/"training.log"
            if file.is_file() and not file.is_symlink():candidates.append(file)
    return max(candidates,key=lambda x:x.stat().st_mtime) if candidates else None

def _log_metrics(file):
    if file is None:return {}
    # 150KB tail only; no unbounded log or user file reads.
    with file.open("rb") as f:
        f.seek(0,2)
        n=f.tell()
        f.seek(max(0,n-150000))
        raw=f.read().decode("utf-8","replace")
    steps=re.findall(r"(?:\bstep\s*[:= ]\s*|\bSTEP\s*=\s*)(\d+)",raw)
    losses=re.findall(r"\bloss\s*[:= ]\s*([0-9]+(?:\.[0-9]+)?)",raw,re.I)
    return {"last_step":int(steps[-1]) if steps else None,
            "loss":float(losses[-1]) if losses else None,
            "loss_points":[float(x) for x in losses[-90:]],
            "log_path":str(file)}

def observation(root):
    path=root/"brain"/"telemetry"/"training.json"
    t=_json(path) or {}
    now=datetime.now(timezone.utc).timestamp()
    try:age=max(0,now-path.stat().st_mtime)
    except OSError:age=None
    pid=t.get("process_id")
    active=_process_active(pid)
    recent=age is not None and age<=20
    # A running status alone is not evidence. Require live process and fresh receipt.
    running=bool(active and recent and t.get("status") in ("running","RUNNING","training","COOLING","SENSOR_HOLD"))
    log=_recent_run(root)
    observed=_log_metrics(log) if log else {}
    step=t.get("actual_steps") if isinstance(t.get("actual_steps"),int) else observed.get("last_step")
    # Older log steps are historical; do not imply present training.
    loss=t.get("loss_metrics",{}).get("loss") if isinstance(t.get("loss_metrics"),dict) else None
    if loss is None:loss=observed.get("loss")
    temp=amd_sensor()
    phase=("REST" if t.get("status") in ("COOLING","SENSOR_HOLD") else "RUNNING") if running else "STALE"
    return {
        "phase":phase,"step":step,"target_steps":t.get("requested_steps"),
        "loss":loss,"loss_points":observed.get("loss_points",[]),
        "gpu_temp":temp.get("gpu_hotspot_c"),
        "gpu_core_temp":temp.get("gpu_core_c"),
        "sensor_source":temp["source"],
        "pid":pid,"pid_active":active,"receipt_age_seconds":age,
        "verified_live":running,
        "run_log":observed.get("log_path"),
        "paused_claim":t.get("status") in ("COOLING","SENSOR_HOLD"),
        "pause_mechanism_verified":False,
        "stop_allowed":False,
    }
