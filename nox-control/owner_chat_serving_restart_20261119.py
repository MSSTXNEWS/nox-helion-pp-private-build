#!/usr/bin/env python3
"""NOX 2026-11-19: one bounded, owner-triggered serving restart; never touch weights or S03."""
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.request

ROOT=Path("/root/nox")
INSTANCE="60509551"
PINS={
    "nox-ds41-8098":3266857,
    "nox-dispatcher-t855u":325385,
    "nox-proxy":331714,
    "nox-web29-18775":242414,
}
RESTART=("nox-proxy","nox-web29-18775")
STOP_PATHS=(
    ROOT/"STOP", ROOT/"STOP.flag", ROOT/"stop.flag", ROOT/".stop",
    ROOT/"program/STOP", ROOT/"state/STOP", ROOT/"state/STOP.flag",
    Path("/workspace/NOX_STOP"), ROOT/"state/OWNER_MAINTENANCE.flag",
)
def emit(phase,data):
    print("NOX_MAINT_REPAIR="+json.dumps({"phase":phase,"data":data},sort_keys=True,separators=(",",":")),flush=True)
def run(args,timeout=20):
    result=subprocess.run(args,capture_output=True,text=True,timeout=timeout,check=False)
    if result.returncode:
        raise RuntimeError("HOLD_SUPERVISOR_COMMAND_FAILED")
    return result.stdout.strip()
def process_start(pid):
    try:
        text=(Path("/proc")/str(pid)/"stat").read_text()
        return int(text.rsplit(") ",1)[1].split()[19])
    except (OSError,ValueError,IndexError):
        raise RuntimeError("HOLD_PROCESS_IDENTITY_MISSING")
def services():
    result={}
    for name in PINS:
        output=run(["supervisorctl","status",name],10)
        m=re.match(r"^"+re.escape(name)+r"\s+([A-Z]+)(?:\s+pid\s+(\d+))?",output)
        if not m or m[1]!="RUNNING" or not m[2]:
            raise RuntimeError("HOLD_SERVICE_NOT_RUNNING_"+name.replace("-","_").upper())
        result[name]={"pid":int(m[2]),"start_ticks":process_start(int(m[2]))}
    return result
def web_get(path):
    try:
        with urllib.request.urlopen(path,timeout=5) as response:
            return int(response.status)
    except urllib.error.HTTPError as e:
        return int(e.code)
    except Exception:
        return 0
def no_model_request_running():
    url="http://127.0.0.1:8098/slots"
    try:
        with urllib.request.urlopen(url,timeout=5) as response:
            slots=json.load(response)
    except Exception:
        raise RuntimeError("HOLD_MODEL_SLOTS_NOT_READABLE")
    if not isinstance(slots,list) or not slots:
        raise RuntimeError("HOLD_MODEL_SLOTS_NOT_LIST")
    if any(not isinstance(s,dict) or "is_processing" not in s for s in slots):
        raise RuntimeError("HOLD_MODEL_SLOTS_UNTRUSTED")
    if any(s["is_processing"] is not False for s in slots):
        raise RuntimeError("HOLD_MODEL_BUSY")
    return len(slots)
def main():
    request=os.environ.get("NOX_OWNER_REQUEST_ID","")
    source=os.environ.get("NOX_OWNER_SOURCE_SHA","")
    if not request.isdecimal() or not re.fullmatch(r"[0-9a-f]{40}",source):
        raise RuntimeError("HOLD_OWNER_REQUEST_INVALID")
    if any(p.exists() or p.is_symlink() for p in STOP_PATHS):
        raise RuntimeError("HOLD_STOP_OR_MAINTENANCE_ACTIVE")
    lock=ROOT/"state/owner_maintenance.lock"
    if not lock.is_file() or lock.is_symlink():
        raise RuntimeError("HOLD_OWNER_LEASE_UNAVAILABLE")
    with open(lock,"rb") as f:
        try:
            fcntl.flock(f,fcntl.LOCK_SH|fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("HOLD_OWNER_EXCLUSIVE_MAINTENANCE")
        before=services()
        if any(before[k]["pid"]!=v for k,v in PINS.items()):
            raise RuntimeError("HOLD_PINNED_PID_CHANGED")
        slots=no_model_request_running()
        health_before={
            "model":web_get("http://127.0.0.1:8098/health"),
            "proxy":web_get("http://127.0.0.1:8080/health"),
            "web":web_get("http://127.0.0.1:18775/nox-web-v29/chat.html"),
        }
        emit("preflight",{"request":request,"slots_idle":slots,"pids":{k:v["pid"] for k,v in before.items()},"http":health_before})
        if health_before["model"]!=200:
            raise RuntimeError("HOLD_MODEL_HEALTH_NOT_200")
        if no_model_request_running()!=slots:
            raise RuntimeError("HOLD_SLOTS_CHANGED")
        completed=[]
        for service in RESTART:
            if any(p.exists() or p.is_symlink() for p in STOP_PATHS):
                raise RuntimeError("HOLD_STOP_RAISED_DURING_RESTART")
            verify=services()
            if any(verify[x]!=before[x] for x in ("nox-ds41-8098","nox-dispatcher-t855u")):
                raise RuntimeError("HOLD_CORE_IDENTITY_CHANGED")
            if service=="nox-proxy" and no_model_request_running()!=slots:
                raise RuntimeError("HOLD_MODEL_BECAME_BUSY")
            run(["supervisorctl","restart",service],55)
            after=services()
            if after[service]["pid"]==verify[service]["pid"]:
                raise RuntimeError("HOLD_RESTART_NO_NEW_PROCESS")
            completed.append({"service":service,"old_pid":verify[service]["pid"],"new_pid":after[service]["pid"]})
            emit("restarted",completed[-1])
        after=services()
        if any(after[x]!=before[x] for x in ("nox-ds41-8098","nox-dispatcher-t855u")):
            raise RuntimeError("HOLD_CORE_CHANGED_AFTER_RESTART")
        health_after={
            "model":web_get("http://127.0.0.1:8098/health"),
            "proxy":web_get("http://127.0.0.1:8080/health"),
            "web":web_get("http://127.0.0.1:18775/nox-web-v29/chat.html"),
        }
        result={"request":request,"restarted":completed,"model_pid_preserved":True,
                "director_pid_preserved":True,"weights_touched":False,"s03_touched":False,"health":health_after,
                "web_http_reachable":health_after["web"] in (200,301,302,303,307,308,401,403)}
        emit("readback",result)
        if health_after["model"]!=200 or health_after["proxy"]!=200 or not result["web_http_reachable"]:
            raise RuntimeError("HOLD_SERVING_HEALTH_AFTER_RESTART")
        print("NOX_MAINT_REPAIR_COMPLETE=true",flush=True)
if __name__=="__main__":
    try:
        main()
    except Exception as e:
        v=str(e)
        code=v if re.fullmatch(r"HOLD_[A-Z0-9_]+",v) else "HOLD_UNEXPECTED_"+type(e).__name__.upper()
        emit("hold",{"reason":code,"automatic_retry":False})
        sys.exit(2)
